import { createContext, useContext, useState, useCallback, type ReactNode } from "react";

interface ActiveProjectContextType {
  activeProjectId: string | null;
  setActiveProjectId: (id: string | null) => void;
  clearActiveProject: () => void;
}

const ActiveProjectContext = createContext<ActiveProjectContextType | undefined>(
  undefined
);

export function ActiveProjectProvider({ children }: { children: ReactNode }) {
  const [activeProjectId, setActiveProjectId] = useState<string | null>(null);

  const clearActiveProject = useCallback(() => {
    setActiveProjectId(null);
  }, []);

  return (
    <ActiveProjectContext.Provider
      value={{ activeProjectId, setActiveProjectId, clearActiveProject }}
    >
      {children}
    </ActiveProjectContext.Provider>
  );
}

export function useActiveProject() {
  const ctx = useContext(ActiveProjectContext);
  if (!ctx) {
    throw new Error(
      "useActiveProject must be used within ActiveProjectProvider"
    );
  }
  return ctx;
}
