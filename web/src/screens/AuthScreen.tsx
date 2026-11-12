import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { authClient } from "../lib/auth-client";
import { Brand, Button, Field, Icon } from "../components/ui";

export default function AuthScreen() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"signin" | "signup">("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [gender, setGender] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    const { error } =
      mode === "signin"
        ? await authClient.signIn.email({ email, password })
        : await authClient.signUp.email({ email, password, name, gender });
    setBusy(false);
    if (error) {
      setError(error.message ?? "Something went wrong");
      return;
    }
    navigate("/");
  }

  async function google() {
    setError("");
    setBusy(true);
    await authClient.signIn.social({
      provider: "google",
      callbackURL: window.location.origin + "/",
    });
    setBusy(false);
  }

  return (
    <div className="app app-auth">
      <form className="screen-pad auth-screen" onSubmit={submit}>
        <Brand />
        <div>
          <div className="eyebrow">
            {mode === "signin" ? "WELCOME BACK" : "JOIN THE CLUB"}
          </div>
          <h2>{mode === "signin" ? "Return to court." : "Find your match."}</h2>
          <p className="muted">
            {mode === "signin"
              ? "Sign in to find your next match."
              : "Create an account to join matches near you."}
          </p>
        </div>
        {mode === "signup" && (
          <>
            <Field
              label="Full name"
              placeholder="Alex Morgan"
              value={name}
              onChange={setName}
            />
            <label className="field">
              <span>Gender</span>
              <span className="input-shell">
                <select
                  value={gender}
                  onChange={(e) => setGender(e.target.value)}
                  aria-label="Gender"
                >
                  <option value="">Select gender</option>
                  <option value="male">Male</option>
                  <option value="female">Female</option>
                  <option value="other">Other</option>
                  <option value="prefer_not_to_say">Prefer not to say</option>
                </select>
              </span>
            </label>
          </>
        )}
        <Field
          label="Email address"
          placeholder="alex@baseline.club"
          type="email"
          value={email}
          onChange={setEmail}
        />
        <Field
          label="Password"
          placeholder="••••••••"
          type="password"
          value={password}
          onChange={setPassword}
        />
        {error && (
          <div className="inline-error">
            <b>Couldn&rsquo;t sign in</b>
            <span>{error}</span>
          </div>
        )}
        <Button type="submit" disabled={busy}>
          {busy ? "Working…" : mode === "signin" ? "Sign in" : "Create account"}
        </Button>
        <div className="or">
          <span />
          OR
          <span />
        </div>
        <Button variant="secondary" onClick={google} disabled={busy}>
          <span className="g-logo">
            <Icon name="arrow" size={15} />
          </span>
          Continue with Google
        </Button>
        <p className="fine-print">
          {mode === "signin" ? "New to Clear?" : "Already have an account?"}{" "}
          <b
            onClick={() => {
              setMode(mode === "signin" ? "signup" : "signin");
              setError("");
            }}
          >
            {mode === "signin" ? "Create account" : "Sign in"}
          </b>
        </p>
      </form>
    </div>
  );
}
