import { SignIn } from "@clerk/nextjs";
import { clerkGlassAppearance } from "@/components/ui/clerk-theme";

export default function SignInPage() {
  return (
    <div className="min-h-[calc(100vh-4rem)] flex items-center justify-center p-4 sm:p-6">
      <div className="w-full max-w-md">
        <SignIn appearance={clerkGlassAppearance} />
      </div>
    </div>
  );
}

