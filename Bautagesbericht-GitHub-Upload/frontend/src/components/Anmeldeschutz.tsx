"use client";

/**
 * Sperrbildschirm vor der eigentlichen App.
 *
 * Ohne gesetztes ``BTB_SEITEN_PASSWORT`` auf dem Server antwortet
 * ``api.zugang.pruefen`` immer mit "ok" — dann ist dieser Bildschirm nie
 * zu sehen und die App verhält sich wie bisher (z. B. auf dem
 * Bürorechner).
 */

import { Loader2, Lock } from "lucide-react";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";

import { api } from "@/lib/api";
import { passwortLesen } from "@/lib/zugang";
import { Button, Card, Input, Label, Meldung } from "@/components/ui";

type Zustand = "pruefe" | "gesperrt" | "frei";

export function Anmeldeschutz({ children }: { children: ReactNode }) {
  const [zustand, setZustand] = useState<Zustand>("pruefe");
  const [eingabe, setEingabe] = useState("");
  const [fehler, setFehler] = useState(false);
  const [sendet, setSendet] = useState(false);

  useEffect(() => {
    let abgebrochen = false;
    api.zugang.pruefen(passwortLesen()).then((ok) => {
      if (!abgebrochen) setZustand(ok ? "frei" : "gesperrt");
    });
    return () => {
      abgebrochen = true;
    };
  }, []);

  async function anmelden(event: FormEvent) {
    event.preventDefault();
    setSendet(true);
    setFehler(false);
    const ok = await api.zugang.pruefen(eingabe);
    setSendet(false);
    if (ok) setZustand("frei");
    else setFehler(true);
  }

  if (zustand === "pruefe") {
    return (
      <div className="flex h-dvh items-center justify-center bg-ui-bg">
        <Loader2 className="size-6 animate-spin text-ui-text-muted" />
      </div>
    );
  }

  if (zustand === "gesperrt") {
    return (
      <div className="flex h-dvh items-center justify-center bg-ui-bg px-4">
        <Card className="w-full max-w-xs p-5">
          <form onSubmit={anmelden} className="space-y-4">
            <div className="flex items-center gap-2 text-ui-accent">
              <Lock size={16} />
              <span className="font-mono text-[11px] tracking-[0.12em] uppercase">
                Zugang geschützt
              </span>
            </div>
            <div>
              <Label>Passwort</Label>
              <div className="mt-1.5">
                <Input
                  type="password"
                  autoFocus
                  value={eingabe}
                  onChange={(e) => setEingabe(e.target.value)}
                  placeholder="•••••••"
                />
              </div>
            </div>
            {fehler && <Meldung art="fehler">Passwort ist nicht richtig.</Meldung>}
            <Button type="submit" disabled={sendet || !eingabe} className="w-full">
              {sendet ? "Prüft…" : "Anmelden"}
            </Button>
          </form>
        </Card>
      </div>
    );
  }

  return <>{children}</>;
}
