// Logs an error the UI already handles. Printed on the server (make logs) and
// in development; silent in the browser in production, where the subject wants
// a clean console. NODE_ENV is inlined at build time, so under `make up` the
// browser bundle compiles this function to an empty one.
export function logError(context: string, err: unknown): void {
  if (typeof window !== "undefined" && process.env.NODE_ENV === "production") return;
  console.error(context, err);
}
