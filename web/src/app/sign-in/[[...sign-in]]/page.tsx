import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <SignIn
          appearance={{
            elements: {
              rootBox: "w-full",
              card: "glass-panel border-white/10 bg-slate-900/80 shadow-2xl",
              headerTitle: "text-slate-100",
              headerSubtitle: "text-slate-400",
              socialButtonsBlockButton: "bg-slate-800 border-white/10 text-slate-200 hover:bg-slate-700",
              formFieldLabel: "text-slate-300",
              formFieldInput: "bg-slate-950/60 border-white/10 text-slate-100",
              formButtonPrimary: "bg-indigo-600 hover:bg-indigo-500 text-white font-medium",
              footerActionLink: "text-indigo-400 hover:text-indigo-300",
            },
          }}
        />
      </div>
    </div>
  );
}
