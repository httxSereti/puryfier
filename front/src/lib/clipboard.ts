/**
 * Copy text to the clipboard, working around browsers/iframes that block
 * the async Clipboard API (e.g. the Chaster iframe, which lacks
 * allow="clipboard-write" — REVIEW.md #22).
 *
 * Returns true on success, false if every method failed.
 */
export async function copyText(text: string): Promise<boolean> {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch {
        // Fall through to the legacy path.
    }

    try {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        const ok = document.execCommand("copy");
        document.body.removeChild(textarea);
        return ok;
    } catch {
        return false;
    }
}
