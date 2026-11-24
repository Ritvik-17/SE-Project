import { useEffect, useRef, useState } from "react";

let rendered = 0;

/** Mermaid diagram drawn with the app's own tokens so it matches both themes. Mermaid loads only when needed. */
export default function Diagram({ code }: { code: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    import("mermaid").then(({ default: mermaid }) => {
      const css = getComputedStyle(document.documentElement);
      const v = (name: string) => css.getPropertyValue(name).trim();
      mermaid.initialize({
        startOnLoad: false, theme: "base",
        themeVariables: {
          fontFamily: v("--font-body"), fontSize: "14px",
          primaryColor: v("--accent-soft"), primaryTextColor: v("--ink"), primaryBorderColor: v("--accent"),
          lineColor: v("--ink-3"), background: v("--surface"), mainBkg: v("--accent-soft"),
          tertiaryColor: v("--sunken"), clusterBkg: v("--sunken"), edgeLabelBackground: v("--surface"),
        },
      });
      // LangGraph hard-codes lavender node fills; drop them so the theme colours apply.
      const themed = code.replace(/^\s*classDef (default|last) .*$/gm, "");
      return mermaid.render(`diagram-${++rendered}`, themed);
    }).then(({ svg }) => {
      if (live && ref.current) ref.current.innerHTML = svg;
    }).catch((e: Error) => live && setError(e.message));
    return () => { live = false; };
  }, [code]);
  if (error) return <pre className="small muted">{code}</pre>;
  return <div ref={ref} className="diagram" />;
}
