import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import axios from "axios";

import type { ChasterExtensionSessionSchema } from "@/types/api";
import PuryfiConnection from "@/components/common/sessions/PuryfiConnection";
import MotdCard from "@/components/common/cards/MotdCard";
import SessionSettings from "@/components/common/sessions/SessionSettings";

export default function Session() {
  const [sessionData, setSessionData] = useState<ChasterExtensionSessionSchema | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const hasFetched = useRef(false);

  useEffect(() => {
    if (hasFetched.current)
      return;

    hasFetched.current = true;

    const fetchSession = async () => {
      try {
        if (!window.location.hash) {
          throw new Error("No login token detected in URL.");
        }

        const hash = window.location.hash.substring(1);
        const params = JSON.parse(decodeURIComponent(hash));

        if (!params.mainToken) {
          throw new Error("mainToken not found in parameters.");
        }

        const backendUrl = import.meta.env.VITE_BACKEND_URL;
        const response = await axios.get(`${backendUrl}/api/session/${params.mainToken}`);
        setSessionData(response.data);
      } catch (err: any) {
        if (axios.isAxiosError(err)) {
          setError(err.response?.data?.detail || "Error syncing with local server.");
        } else {
          setError(err.message || "Error parsing parameters");
        }
      } finally {
        setIsLoading(false);
      }
    };

    fetchSession();
  }, []);

  if (error) {
    return (
      <div className="flex flex-col w-full min-h-screen bg-[#2a2736] p-3 sm:p-6 ">
        <div className="mx-auto w-full flex flex-col gap-6">
          <MotdCard />

          <div className="flex-1 bg-[#14131A] rounded-2xl p-1 flex flex-col items-center relative overflow-hidden">
            <div className="flex flex-col items-center text-center space-y-6 w-full mx-auto relative z-10">
              <div className="flex flex-col items-center justify-center py-12 space-y-4">
                <p className="text-sm text-red-400 font-medium">An error occurred</p>
                <p className="text-sm font-black text-slate-400 uppercase tracking-wider">{error}</p>
                <p className="text-sm font-black text-slate-500 uppercase tracking-wider">Please try again later.</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col w-full min-h-screen bg-[#2a2736] p-3 sm:p-6 ">
      <div className="mx-auto w-full flex flex-col gap-6">

        <MotdCard />

        <div className="flex flex-col md:flex-row gap-6 w-full items-stretch flex-1">
          <div className="flex-1 bg-[#14131A] rounded-2xl p-1 flex flex-col items-center relative overflow-hidden">
            <div className="flex flex-col items-center text-center w-full mx-auto relative z-10">

              <div className="flex flex-row justify-between items-center w-full p-3">
                <h1 className="text-xl font-bold tracking-tight text-white">
                  Puryfier
                  <span className="text-slate-500 text-sm ml-2 font-normal">[v{import.meta.env.VITE_APP_VERSION}]</span>
                </h1>
                <div className="flex items-center space-x-2">
                  {sessionData && (
                    <span className={`px-3 py-1 text-xs font-bold uppercase tracking-wider rounded-full border ${sessionData.role === 'wearer'
                      ? 'bg-rose-500/20 text-rose-400 border-rose-500/30'
                      : 'bg-purple-500/20 text-purple-400 border-purple-500/30'
                      }`}>
                      {sessionData.role}
                    </span>
                  )}
                </div>
              </div>

              {isLoading ? (
                <div className="flex flex-col items-center justify-center py-12 space-y-2">
                  <Loader2 className="w-10 h-10 text-purple-500 animate-spin" />
                  <p className="text-sm text-slate-400 animate-pulse font-medium">Loading...</p>
                </div>
              ) : sessionData ? (
                <div className="w-full flex flex-col gap-6 p-3">

                  <PuryfiConnection session={sessionData} />

                  <SessionSettings session={sessionData} />
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
