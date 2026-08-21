import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

export type ToastType = "success" | "error" | "info";

interface ToastItem {
  id: number;
  message: string;
  type: ToastType;
}

interface ToastContextValue {
  toast: (message: string, type?: ToastType) => void;
  success: (message: string) => void;
  error: (message: string) => void;
  info: (message: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

let toastId = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const removalTimers = useRef(
    new Map<number, ReturnType<typeof setTimeout>>()
  );

  const remove = useCallback((id: number) => {
    const timer = removalTimers.current.get(id);
    if (timer !== undefined) {
      clearTimeout(timer);
      removalTimers.current.delete(id);
    }
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const add = useCallback(
    (message: string, type: ToastType = "info") => {
      const id = ++toastId;
      setItems((prev) => [...prev, { id, message, type }]);
      const timer = setTimeout(() => remove(id), 3200);
      removalTimers.current.set(id, timer);
    },
    [remove]
  );

  useEffect(
    () => () => {
      removalTimers.current.forEach((timer) => clearTimeout(timer));
      removalTimers.current.clear();
    },
    []
  );

  const value = useMemo<ToastContextValue>(
    () => ({
      toast: add,
      success: (message) => add(message, "success"),
      error: (message) => add(message, "error"),
      info: (message) => add(message, "info"),
    }),
    [add]
  );

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`toast toast-${t.type}`}>
            {t.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
