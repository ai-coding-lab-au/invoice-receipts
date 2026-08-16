import { AxiosError } from "axios";

// Field names as the API spells them -> what the operator sees on the form.
const FIELD_LABELS: Record<string, string> = {
  id: "Short ID",
  display_name: "Name",
  legal_name: "Legal name",
  trading_name: "Business name",
  abn: "ABN",
  acn: "ACN",
  postcode: "Postcode",
  email: "Email",
  website: "Website",
  phone: "Phone",
  address: "Address",
  client_ref: "Client reference",
  notes: "Notes",
  full_name: "Full name",
  registration_number: "Registration number",
  doc_number_override: "Document number",
  operator: "Operator",
  reason: "Reason",
  description: "Description",
  unit_price: "Unit price",
  quantity: "Quantity",
  fee: "Fee",
  amount: "Amount",
  issue_date: "Issue date",
  due_date: "Due date",
  date_of_birth: "Date of birth",
};

function labelFor(loc: unknown): string | null {
  if (!Array.isArray(loc)) return null;
  // Pydantic's loc is like ["body", "acn"] or ["body", "lines", 0, "description"].
  const named = [...loc].reverse().find((part) => typeof part === "string" && part !== "body");
  if (typeof named !== "string") return null;
  return FIELD_LABELS[named] ?? named.replace(/_/g, " ");
}

/**
 * Turn a raw pydantic message into something an operator can act on.
 *
 * The API surfaced strings like `String should match pattern
 * '^[a-z0-9][a-z0-9_-]*$'` and `String should have at most 200 characters`,
 * which name neither the field nor the actual rule in plain words.
 */
function humanise(msg: string, field: string | null): string {
  const withField = (text: string) => (field ? `${field}: ${text}` : text);

  const tooLong = /String should have at most (\d+) characters/.exec(msg);
  if (tooLong) return withField(`must be ${tooLong[1]} characters or fewer.`);

  const tooShort = /String should have at least (\d+) characters/.exec(msg);
  if (tooShort) {
    return withField(
      tooShort[1] === "1"
        ? "cannot be blank."
        : `must be at least ${tooShort[1]} characters.`,
    );
  }

  if (/String should match pattern '\^\[a-z0-9\]\[a-z0-9_-\]\*\$'/.test(msg)) {
    return withField(
      "use lowercase letters, numbers, hyphens and underscores only, starting with a letter or number (no spaces).",
    );
  }

  const pattern = /String should match pattern '(.+)'/.exec(msg);
  if (pattern) return withField(`is not in the expected format (${pattern[1]}).`);

  const gt = /Input should be greater than (\S+)/.exec(msg);
  if (gt) return withField(`must be greater than ${gt[1]}.`);

  const ge = /Input should be greater than or equal to (\S+)/.exec(msg);
  if (ge) return withField(`must be ${ge[1]} or more.`);

  const le = /Input should be less than or equal to (\S+)/.exec(msg);
  if (le) return withField(`must be ${le[1]} or less.`);

  const decimals = /Decimal input should have no more than (\d+) decimal places?/.exec(msg);
  if (decimals) return withField(`can have at most ${decimals[1]} decimal places.`);

  if (/Input should be a valid (number|decimal|integer)/.test(msg)) {
    return withField("must be a number.");
  }
  if (/Input should be a valid date/.test(msg)) return withField("must be a valid date.");
  if (/Field required/.test(msg)) return withField("is required.");

  // Our own validators already read as sentences; just prefix the field.
  return field && !msg.toLowerCase().startsWith(field.toLowerCase())
    ? `${field}: ${msg}`
    : msg;
}

export function apiErrorMessage(err: unknown, fallback = "Request failed"): string {
  if (err instanceof AxiosError) {
    const detail = err.response?.data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      // Report every field that failed, not just the first, so a form with two
      // problems does not need two round trips to fix.
      const messages = detail
        .map((item) =>
          typeof item?.msg === "string"
            ? humanise(item.msg.replace(/^Value error,\s*/, ""), labelFor(item.loc))
            : null,
        )
        .filter((text): text is string => !!text)
        // Terminate each one so several problems read as separate sentences
        // rather than running together.
        .map((text) => (/[.!?]$/.test(text) ? text : `${text}.`));
      const unique = [...new Set(messages)];
      if (unique.length) return unique.join(" ");
    }
    if (typeof err.message === "string" && err.message) return err.message;
  }
  if (err instanceof Error) return err.message || fallback;
  if (typeof err === "string") return err;
  return fallback;
}

/**
 * Friendly message for an AI-backed action (extract/generate/rewrite) when the
 * local LLM service is unreachable — a 502 from the proxy or a connection
 * refused, which the raw axios message ("Request failed with status code 502")
 * doesn't explain. `action` describes what failed, e.g. "extract fields".
 */
export function aiErrorMessage(err: unknown, action: string): string {
  const aiDown =
    err instanceof AxiosError &&
    (err.response?.status === 502 ||
      err.response?.status === 503 ||
      err.code === "ERR_NETWORK");
  if (aiDown) {
    return `Could not ${action}: the local AI service (Ollama) is not responding. Start it and try again.`;
  }
  return apiErrorMessage(err);
}
