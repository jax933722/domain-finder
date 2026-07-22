import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Globe, Loader2 } from "lucide-react";
import { authApi, apiError } from "@/lib/api";
import { useToast } from "@/hooks/useToast";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export function ForgotPasswordPage() {
  const { toast } = useToast();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [resetToken, setResetToken] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  // Reset step
  const [newPassword, setNewPassword] = useState("");
  const [done, setDone] = useState(false);

  const requestReset = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const res = await authApi.forgotPassword(email);
      setSent(true);
      // In non-production the API returns the token so the flow is testable.
      setResetToken(res.reset_token);
      toast(res.message, "info");
    } catch (err) {
      toast(apiError(err), "error");
    } finally {
      setLoading(false);
    }
  };

  const submitNewPassword = async (e: FormEvent) => {
    e.preventDefault();
    if (!resetToken) return;
    setLoading(true);
    try {
      await authApi.resetPassword(resetToken, newPassword);
      setDone(true);
      toast("Password updated. You can now sign in.", "success");
    } catch (err) {
      toast(apiError(err), "error");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-background to-secondary p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="items-center text-center">
          <span className="mb-2 flex h-12 w-12 items-center justify-center rounded-xl bg-primary text-primary-foreground">
            <Globe className="h-7 w-7" />
          </span>
          <CardTitle className="text-2xl">Reset password</CardTitle>
          <CardDescription>
            {done
              ? "Your password has been updated."
              : sent
                ? "Enter a new password below."
                : "We'll send you a reset link."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {done ? (
            <Link to="/login">
              <Button className="w-full">Back to sign in</Button>
            </Link>
          ) : !sent ? (
            <form onSubmit={requestReset} className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input
                  id="email"
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@company.com"
                />
              </div>
              <Button type="submit" className="w-full" disabled={loading}>
                {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                Send reset link
              </Button>
            </form>
          ) : (
            <form onSubmit={submitNewPassword} className="space-y-4">
              {resetToken && (
                <p className="rounded-md bg-muted p-3 text-xs text-muted-foreground">
                  Dev mode: reset token auto-filled. In production this arrives by email.
                </p>
              )}
              <div className="space-y-2">
                <Label htmlFor="newPassword">New password</Label>
                <Input
                  id="newPassword"
                  type="password"
                  required
                  minLength={8}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder="At least 8 characters"
                />
              </div>
              <Button type="submit" className="w-full" disabled={loading || !resetToken}>
                {loading && <Loader2 className="h-4 w-4 animate-spin" />}
                Update password
              </Button>
            </form>
          )}
          <p className="mt-6 text-center text-sm text-muted-foreground">
            <Link to="/login" className="font-medium text-primary hover:underline">
              Back to sign in
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
