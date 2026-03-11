function App() {
  return (
    <div className="min-h-screen bg-gray-950 text-white">
      <header className="border-b border-gray-800 px-6 py-4">
        <div className="mx-auto flex max-w-4xl items-center justify-between">
          <h1 className="text-lg font-bold">WatermarkOff</h1>
          <nav className="flex gap-4 text-sm text-gray-400">
            <a href="#how" className="hover:text-white">How it works</a>
            <a href="#faq" className="hover:text-white">FAQ</a>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-4xl px-6 py-16 text-center">
        <h2 className="text-3xl font-bold">Remove Watermarks Instantly</h2>
        <p className="mt-2 text-gray-400">Images & PDFs — free, no signup</p>
      </main>
    </div>
  );
}

export default App;
