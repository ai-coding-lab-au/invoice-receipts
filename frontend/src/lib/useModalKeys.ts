import { useEffect, useRef } from "react";
import type { RefObject } from "react";

const modalStack: symbol[] = [];

export function useModalKeys({
  open,
  onClose,
  onSubmit,
  containerRef,
}: {
  open: boolean;
  onClose: () => void;
  onSubmit?: () => void;
  containerRef?: RefObject<HTMLElement>;
}) {
  const idRef = useRef(Symbol("modal"));
  const onCloseRef = useRef(onClose);
  const onSubmitRef = useRef(onSubmit);

  useEffect(() => {
    onCloseRef.current = onClose;
    onSubmitRef.current = onSubmit;
  }, [onClose, onSubmit]);

  useEffect(() => {
    if (!open) return;

    const id = idRef.current;
    modalStack.push(id);

    const handler = (e: KeyboardEvent) => {
      if (modalStack[modalStack.length - 1] !== id) return;

      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        onCloseRef.current();
        return;
      }

      if (e.key === "Tab" && containerRef?.current) {
        const focusable = Array.from(
          containerRef.current.querySelectorAll<HTMLElement>(
            'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
          ),
        ).filter(
          (element) =>
            element.getAttribute("aria-hidden") !== "true" &&
            element.offsetParent !== null,
        );
        if (focusable.length === 0) {
          e.preventDefault();
          containerRef.current.focus();
          return;
        }

        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        const active = document.activeElement;
        if (e.shiftKey && (active === first || !containerRef.current.contains(active))) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && (active === last || !containerRef.current.contains(active))) {
          e.preventDefault();
          first.focus();
        }
        return;
      }

      if (e.key === "Enter" && onSubmitRef.current) {
        const target = e.target as HTMLElement | null;
        const tag = target?.tagName?.toLowerCase();
        if (tag === "textarea" || tag === "button" || tag === "select") return;
        if (target?.isContentEditable) return;
        e.preventDefault();
        e.stopPropagation();
        onSubmitRef.current();
      }
    };

    window.addEventListener("keydown", handler);
    return () => {
      window.removeEventListener("keydown", handler);
      const idx = modalStack.lastIndexOf(id);
      if (idx >= 0) modalStack.splice(idx, 1);
    };
  }, [open, containerRef]);
}
