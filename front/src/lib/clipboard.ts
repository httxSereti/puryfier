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

    let textarea: HTMLTextAreaElement | null = null;

    try {
        textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.style.position = "fixed";
        textarea.style.opacity = "0";
        document.body.appendChild(textarea);
        textarea.focus();
        textarea.select();
        return document.execCommand("copy");
    } catch {
        return false;
    } finally {
        textarea?.remove();
    }
}
