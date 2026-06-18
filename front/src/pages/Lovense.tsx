import { WasmDemo } from "@/components/common/lovense/wasm-connect";

export default function LovensePage() {


    return (
        <div className="flex flex-col w-full min-h-screen bg-[#2a2736] text-slate-100 p-4 sm:p-8 font-sans">
            <div className="flex flex-col items-center text-center space-y-6 max-w-3xl mx-auto w-full">
                <div className="space-y-2">
                    <h1 className="text-2xl font-bold tracking-tight text-white">
                        Lovense
                    </h1>
                    
                    <WasmDemo />
                </div>
            </div>
        </div>
    );
}