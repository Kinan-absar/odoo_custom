/** @odoo-module **/
/** Preserve the underlying OWL/RPC cause instead of displaying only its wrapper. */
export function describePurchaseError(error) {
    const seen = new Set();
    const messages = [];
    const details = [];
    for (let current = error; current && !seen.has(current) && seen.size < 8; current = current.cause) {
        seen.add(current);
        const message = current.data?.message || current.message || String(current);
        if (message && !messages.includes(message)) messages.push(message);
        const stack = current.data?.debug || current.stack;
        if (stack) details.push(String(stack));
    }
    return {
        message: messages.join("\n") || "Purchase could not start.",
        details: details.join("\n\n"),
    };
}
