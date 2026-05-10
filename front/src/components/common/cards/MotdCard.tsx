export default function MotdCard() {

    return (
        <div className="w-full bg-cyan-950/40 border border-cyan-800/50 rounded-2xl p-4 flex items-center justify-between shadow-lg backdrop-blur-sm">
            <div className="flex items-center gap-4">
                <div className="p-3 bg-cyan-900/50 rounded-xl shadow-inner">
                    <span className="text-xl">✨</span>
                </div>
                <div>
                    <h2 className="font-bold text-cyan-50 text-sm sm:text-base">Information</h2>
                    <p className="text-xs sm:text-sm text-cyan-200/80">The extension is currently in development. Some features may not work as expected.</p>
                </div>
            </div>
            {/* <button className="text-cyan-400 hover:text-cyan-300 text-sm font-semibold px-4 py-2 bg-cyan-950/50 rounded-lg border border-cyan-800/50 transition-colors hidden sm:block">
                More information
            </button> */}
        </div>
    )
}