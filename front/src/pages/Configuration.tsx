import { useEffect, useRef, useState } from "react";
import { Loader2, ShieldCheck } from "lucide-react";
import axios from "axios";
import type { ChasterExtensionConfigurationSchema } from "@/types/chaster";
import ConfigurationOptions from "@/components/common/configuration/ConfigurationOptions";

function postToParent(event: string, payload?: object) {
  window.parent.postMessage(
    JSON.stringify({ type: "partner_configuration", event, ...(payload ? { payload } : {}) }),
    "*"
  );
}

export default function Configuration() {
  const [configurationData, setConfigurationData] = useState<ChasterExtensionConfigurationSchema | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Keep a mutable ref to the latest config & token so the event listener always has fresh values
  const configRef = useRef<ChasterExtensionConfigurationSchema | null>(null);
  const tokenRef = useRef<string>("");
  const hasFetched = useRef(false);

  useEffect(() => {
    postToParent("capabilities", { features: { save: true } });
  }, []);

  useEffect(() => {
    // Don't fetch session twice (react strict mode re-renders the component on development)
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

        if (!params.partnerConfigurationToken) {
          throw new Error("partnerConfigurationToken not found in parameters.");
        }

        tokenRef.current = params.partnerConfigurationToken;

        const backendUrl = import.meta.env.VITE_BACKEND_URL || "http://localhost:8090";
        const response = await axios.get(`${backendUrl}/api/extensions/configuration/${params.partnerConfigurationToken}`);
        setConfigurationData(response.data);
        console.log(response.data)
        configRef.current = response.data;
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

  useEffect(() => {
    const handleMessage = async (e: MessageEvent) => {
      if (typeof e.data !== "string") return;

      let parsed: { type?: string; event?: string };
      try {
        parsed = JSON.parse(e.data);
      } catch {
        return;
      }

      if (parsed.type !== "chaster" || parsed.event !== "partner_configuration_save") return;

      // Show spinner on the Chaster modal
      postToParent("save_loading");

      try {
        const backendUrl = import.meta.env.VITE_BACKEND_URL || "http://localhost:8090";

        await axios.put(
          `${backendUrl}/api/extensions/configuration/${tokenRef.current}`,
          configRef.current?.config ?? {},
        );

        // Signal success — Chaster will close the modal
        postToParent("save_success");
      } catch (err: any) {
        // Stop spinner and keep modal open
        postToParent("save_failed");
        const detail = axios.isAxiosError(err)
          ? err.response?.data?.detail || "Save failed."
          : "Unexpected error.";
        setError(detail);
      }
    };

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, []);


  return (
    <div className="flex flex-col w-full min-h-screen bg-[#2a2736] text-slate-100 p-4 sm:p-8 font-sans">
      <div className="flex flex-col items-center text-center space-y-6 max-w-3xl mx-auto w-full">

        <div className="p-4 bg-cyan-950/30 rounded-full border border-cyan-900/50 shadow-inner">
          <svg className="w-10 h-10 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
        </div>

        <div className="space-y-2">
          <h1 className="text-2xl font-bold tracking-tight text-white">
            Puryfi Chaster Linker
          </h1>
          <p className="text-sm text-slate-400">
            Sync your Chaster lock with Puryfi
          </p>
        </div>

        <div className="w-full h-[1px] bg-slate-800" />

        {error ? (
          <div className="w-full p-4 bg-red-950/50 border border-red-900/50 rounded-xl">
            <p className="text-sm text-red-400 font-medium">{error}</p>
          </div>
        ) : isLoading ? (
          <div className="flex flex-col items-center justify-center py-6 space-y-4">
            <Loader2 className="w-8 h-8 text-cyan-500 animate-spin" />
            <p className="text-sm text-slate-400 animate-pulse">Fetching session...</p>
          </div>
        ) : configurationData ? (
          <div className="w-full space-y-4">
            <div className="w-full p-4 flex justify-between bg-slate-950 border border-slate-800 rounded-xl space-y-3 items-center">
              <div className="flex items-center gap-3">
                <ShieldCheck className="w-5 h-5 text-slate-400" />
                <p className="text-sm font-semibold text-slate-200">Puryfi Link:</p>
                {configurationData.is_online ? (
                  <span className="text-sm font-semibold text-emerald-400">Connected</span>
                ) : (
                  <span className="text-sm font-semibold text-red-400">Disconnected</span>
                )}
              </div>
              <div className="flex items-center justify-center">
              </div>
            </div>

            <ConfigurationOptions
              config={configurationData.config}
              onChange={(updatedConfig) => {
                setConfigurationData({
                  ...configurationData,
                  config: updatedConfig
                });
                configRef.current = {
                  ...configurationData,
                  config: updatedConfig
                };
              }}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}