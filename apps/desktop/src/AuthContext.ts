import { createContext, useContext } from "react";

import type { AuthSession } from "./auth";

export interface AuthContextValue {
  apiUrl: string;
  session: AuthSession;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextValue | null>(null);

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (!value) {
    throw new Error("useAuth must be used inside AuthGate");
  }
  return value;
}
