import { AuthForm } from "@/components/auth/AuthForm";
import { Heading } from "@/components/ui/Heading";

interface LoginPageProps {
  searchParams?: Promise<{ next?: string | string[] }>;
}

// Where proxy.ts sends a logged-out visitor of a protected page: both ways in
// (email or 42), then back to `next`. AuthModalContext checks `next` is a path
// on this site before following it.
export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = await searchParams;
  const next = typeof params?.next === "string" ? params.next : "/";

  return (
    <main className="max-w-md mx-auto px-4 sm:px-6 py-12">
      <div className="bg-white rounded-2xl shadow-sm border border-slate-100 p-6 space-y-5">
        <Heading level={2}>Connexion</Heading>
        <AuthForm next={next} />
      </div>
    </main>
  );
}
