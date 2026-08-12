import Link from "next/link";

export default function NotFound() {
  return (
    <div className="min-h-[70vh] flex items-center justify-center p-8">
      <div className="text-center max-w-md">
        <div className="h-2 bg-header-grad rounded-t-lg mb-6" />
        <div className="text-4xl mb-4">&#x1F311;</div>
        <h1 className="font-noto-telugu text-2xl text-text-primary mb-1">
          పేజీ కనుగొనబడలేదు
        </h1>
        <p className="font-playfair italic text-text-secondary mb-6">
          Page not found
        </p>
        <Link
          href="/"
          className="px-6 py-3 rounded-lg bg-accent text-white font-lora text-sm font-semibold inline-block hover:opacity-90 transition-opacity min-h-[44px]"
        >
          Go to Today
        </Link>
      </div>
    </div>
  );
}
