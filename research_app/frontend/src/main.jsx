import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowUp,
  BookOpen,
  CheckCircle2,
  CircleStop,
  ExternalLink,
  FileSearch,
  FlaskConical,
  Github,
  LoaderCircle,
  Plus,
  Quote,
  Search,
  Sparkles,
} from "lucide-react";
import "./styles.css";

const starters = [
  "What Vietnamese pretrained language models are available?",
  "Find datasets and SOTA methods for Vietnamese NLP",
  "Compare hybrid retrieval and reranking for legal QA",
];

function Markdown({ children }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        a: ({ children, ...props }) => (
          <a {...props} target="_blank" rel="noreferrer">
            {children} <ExternalLink size={12} />
          </a>
        ),
      }}
    >
      {children}
    </ReactMarkdown>
  );
}

function App() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState([]);
  const [streaming, setStreaming] = useState(false);
  const [sessionId, setSessionId] = useState(
    () => localStorage.getItem("research-session") || "",
  );
  const abortRef = useRef(null);
  const bottomRef = useRef(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, status]);

  const appendAssistant = (chunk) => {
    setMessages((current) => {
      const next = [...current];
      const last = next.at(-1);
      if (last?.role === "assistant" && last.streaming) {
        next[next.length - 1] = { ...last, content: last.content + chunk };
      } else {
        next.push({ role: "assistant", content: chunk, streaming: true });
      }
      return next;
    });
  };

  async function send(prefilled) {
    const message = (prefilled ?? input).trim();
    if (!message || streaming) return;
    setInput("");
    setStatus([]);
    setMessages((current) => [...current, { role: "user", content: message }]);
    setStreaming(true);
    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch("/api/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, session_id: sessionId || null }),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        throw new Error(`API returned ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
          if (!line.trim()) continue;
          const event = JSON.parse(line);
          if (event.type === "session") {
            setSessionId(event.session_id);
            localStorage.setItem("research-session", event.session_id);
          } else if (event.type === "status") {
            setStatus((current) => [...current, event.content.trim()]);
          } else if (event.type === "content") {
            appendAssistant(event.content);
          } else if (event.type === "error") {
            throw new Error(event.message);
          }
        }
      }
    } catch (error) {
      if (error.name !== "AbortError") {
        appendAssistant(`\n\n**Request failed:** ${error.message}`);
      }
    } finally {
      setStreaming(false);
      setMessages((current) =>
        current.map((item) => ({ ...item, streaming: false })),
      );
      abortRef.current = null;
    }
  }

  function newSession() {
    abortRef.current?.abort();
    localStorage.removeItem("research-session");
    setSessionId("");
    setMessages([]);
    setStatus([]);
    setStreaming(false);
  }

  return (
    <div className="app-shell">
      <aside>
        <div className="brand">
          <div className="brand-mark"><FlaskConical size={20} /></div>
          <div>
            <strong>Academic Paper Agent</strong>
            <span>Evidence-backed research</span>
          </div>
        </div>

        <button className="new-chat" onClick={newSession}>
          <Plus size={16} /> New research
        </button>

        <div className="source-panel">
          <p>LIVE SOURCES</p>
          <div><span className="source-dot arxiv" /> arXiv <small>Free</small></div>
          <div><span className="source-dot scholar" /> Semantic Scholar</div>
        </div>

        <div className="pipeline">
          <p>RESEARCH PIPELINE</p>
          {[
            [Search, "Multi-source search"],
            [FileSearch, "Rank & deduplicate"],
            [BookOpen, "Read evidence"],
            [Quote, "Critique claims"],
          ].map(([Icon, label]) => (
            <div key={label}><Icon size={15} /> {label}</div>
          ))}
        </div>

        <a className="repo-link" href="https://github.com" target="_blank">
          <Github size={15} /> Project repository
        </a>
      </aside>

      <main>
        <header>
          <div>
            <span className="eyebrow">ACADEMIC PAPER RESEARCH AGENT</span>
            <h1>
              Ask better questions.<br />
              <span className="hero-accent">Find grounded answers.</span>
            </h1>
          </div>
          <div className="online"><span /> API online</div>
        </header>

        <section className="conversation">
          {messages.length === 0 ? (
            <div className="welcome">
              <div className="orb"><Sparkles size={28} /></div>
              <h2>What should we investigate?</h2>
              <p>
                Search academic sources, compare methods, uncover limitations,
                and build a citation-ready research brief.
              </p>
              <div className="starters">
                {starters.map((starter) => (
                  <button key={starter} onClick={() => send(starter)}>
                    {starter}<ArrowUp size={14} />
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message, index) => (
              <article
                className={`message ${message.role} ${message.streaming ? "is-streaming" : ""}`}
                key={index}
              >
                <div className="message-label">
                  {message.role === "user" ? "YOU" : "ACADEMIC PAPER AGENT"}
                </div>
                {message.role === "assistant" ? (
                  <Markdown>{message.content}</Markdown>
                ) : (
                  <p>{message.content}</p>
                )}
              </article>
            ))
          )}

          {streaming && status.length > 0 && (
            <div className="status-card">
              <div className="status-head">
                <LoaderCircle className="spin" size={16} />
                Researching live
              </div>
              {status.slice(-4).map((item, index) => (
                <div className="status-line" key={`${item}-${index}`}>
                  <CheckCircle2 size={13} /> {item}
                </div>
              ))}
            </div>
          )}
          <div ref={bottomRef} />
        </section>

        <footer>
          <div className="composer">
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  send();
                }
              }}
              placeholder="Ask a research question or request citations…"
              rows={1}
            />
            {streaming ? (
              <button
                className="send stop"
                aria-label="Stop"
                onClick={() => abortRef.current?.abort()}
              >
                <CircleStop size={18} />
              </button>
            ) : (
              <button className="send" aria-label="Send" onClick={() => send()}>
                <ArrowUp size={18} />
              </button>
            )}
          </div>
          <p className="hint">Enter to send · Shift + Enter for a new line</p>
        </footer>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode><App /></React.StrictMode>,
);
