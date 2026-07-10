import { NextRequest } from "next/server";
import { spawn } from "child_process";
import path from "path";

export const dynamic = "force-dynamic";

export async function GET(req: NextRequest) {
  const encoder = new TextEncoder();
  
  const stream = new ReadableStream({
    start(controller) {
      // The dashboard is at <root>/dashboard, so the root is one level up
      const rootDir = path.resolve(process.cwd(), "..");
      
      const cmd = "source venv/bin/activate && python run.py simulate && python run.py synthesis && python run.py deck && python extract_deck.py";
      
      const child = spawn(cmd, {
        cwd: rootDir,
        shell: "/bin/bash",
      });

      controller.enqueue(encoder.encode(`data: Starting pipeline...\n\n`));
      controller.enqueue(encoder.encode(`data: CWD: ${rootDir}\n\n`));
      
      child.stdout.on("data", (data) => {
        const text = data.toString();
        const lines = text.split("\n");
        for (const line of lines) {
          if (line) {
            controller.enqueue(encoder.encode(`data: ${line}\n\n`));
          }
        }
      });

      child.stderr.on("data", (data) => {
        const text = data.toString();
        const lines = text.split("\n");
        for (const line of lines) {
          if (line) {
            controller.enqueue(encoder.encode(`data: ${line}\n\n`));
          }
        }
      });

      child.on("close", (code) => {
        controller.enqueue(encoder.encode(`data: Pipeline finished with code ${code}\n\n`));
        controller.close();
      });

      child.on("error", (err) => {
        controller.enqueue(encoder.encode(`data: ERROR: ${err.message}\n\n`));
        controller.close();
      });
    }
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text-event-stream",
      "Cache-Control": "no-cache",
      "Connection": "keep-alive",
    },
  });
}
