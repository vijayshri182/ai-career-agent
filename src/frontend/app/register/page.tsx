import { AuthForm } from "@/components/auth-form";

export default function RegisterPage() {
  return (
    <div className="flex flex-1 items-center justify-center bg-zinc-50 px-4 py-16">
      <AuthForm mode="register" />
    </div>
  );
}