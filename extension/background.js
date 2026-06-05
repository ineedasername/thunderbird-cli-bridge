// tbcli Bridge — Thunderbird Extension Background Script
// Routes commands from native messaging host to Thunderbird APIs

let port = null;

function connectNativeHost() {
  port = browser.runtime.connectNative("tbcli_host");
  port.onMessage.addListener(handleMessage);
  port.onDisconnect.addListener(() => {
    console.log("tbcli: native host disconnected, reconnecting in 2s...");
    port = null;
    setTimeout(connectNativeHost, 2000);
  });
  console.log("tbcli: connected to native host");
}

async function handleMessage(msg) {
  const { id, command, args } = msg;
  let result;
  try {
    result = { id, ok: true, data: await dispatch(command, args || {}) };
  } catch (e) {
    result = { id, ok: false, error: String(e) };
  }
  if (port) port.postMessage(result);
}

async function dispatch(command, args) {
  switch (command) {
    case "status":
      return { status: "connected", version: "1.0.0" };

    case "accounts": {
      const accounts = await browser.accounts.list();
      return accounts.map(a => ({
        id: a.id,
        name: a.name,
        type: a.type,
        identities: a.identities.map(i => ({ email: i.email, name: i.name }))
      }));
    }

    case "folders": {
      const accounts = await browser.accounts.list();
      let target = accounts;
      if (args.account) {
        target = accounts.filter(a =>
          a.id === args.account || a.name.toLowerCase().includes(args.account.toLowerCase())
        );
      }
      const result = [];
      for (const acct of target) {
        const allFolders = await getAllFolders(acct);
        const folders = allFolders.map(f => ({
          id: f.id,
          name: f.name,
          path: f.path,
          specialUse: f.specialUse || [],
        }));
        result.push({ account: acct.name, accountId: acct.id, folders });
      }
      return result;
    }

    case "list": {
      const folder = await resolveFolder(args.folder || "Inbox");
      const hasFilters = args.unread || args.after || args.before || args.from || args.to || args.subject || args.body || args.flagged;

      let msgs;
      if (hasFilters) {
        // Use query() for server-side filtering
        const q = { folderId: folder.id };
        if (args.unread) q.read = false;
        if (args.flagged) q.flagged = true;
        if (args.after) q.fromDate = new Date(args.after);
        if (args.before) q.toDate = new Date(args.before);
        if (args.from) q.author = args.from;
        if (args.to) q.recipients = args.to;
        if (args.subject) q.subject = args.subject;
        if (args.body) q.body = args.body;
        msgs = await collectPages(browser.messages.query(q), args.limit || 25);
      } else {
        msgs = await collectPages(browser.messages.list(folder.id), args.limit || 25);
      }

      return msgs.map(summarizeMessage);
    }

    case "read": {
      const msgId = Number(args.id);
      const msg = await browser.messages.get(msgId);
      const full = await browser.messages.getFull(msgId);
      const body = extractBody(full, args.format || "text");
      return { ...summarizeMessage(msg), body };
    }

    case "search": {
      const q = {};
      if (args.query) q.fullText = args.query;
      if (args.folder) {
        const folder = await resolveFolder(args.folder);
        q.folderId = folder.id;
      }
      if (args.unread) q.read = false;
      if (args.after) q.fromDate = new Date(args.after);
      if (args.before) q.toDate = new Date(args.before);
      if (args.from) q.author = args.from;
      if (args.to) q.recipients = args.to;
      if (args.subject) q.subject = args.subject;
      if (args.body) q.body = args.body;
      const msgs = await collectPages(browser.messages.query(q), args.limit || 25);
      return msgs.map(summarizeMessage);
    }

    case "move": {
      const dest = await resolveFolder(args.folder);
      await browser.messages.move([Number(args.id)], dest.id);
      return { moved: true };
    }

    case "delete": {
      await browser.messages.delete(
        [Number(args.id)],
        { deletePermanently: !!args.permanent }
      );
      return { deleted: true };
    }

    case "flag": {
      await browser.messages.update(Number(args.id), { flagged: true });
      return { flagged: true };
    }

    case "mark-read": {
      await browser.messages.update(Number(args.id), { read: true });
      return { read: true };
    }

    case "send": {
      const details = {
        to: Array.isArray(args.to) ? args.to : [args.to],
        subject: args.subject,
      };
      if (args.cc) details.cc = Array.isArray(args.cc) ? args.cc : [args.cc];
      if (args.bcc) details.bcc = Array.isArray(args.bcc) ? args.bcc : [args.bcc];
      if (args.html) {
        details.isPlainText = false;
        details.body = args.body;
      } else {
        details.isPlainText = true;
        details.plainTextBody = args.body;
      }
      // beginNew signature: (messageId?, details?) — pass null for no template
      const tab = await browser.compose.beginNew(null, details);
      await browser.compose.sendMessage(tab.id, { mode: "sendNow" });
      return { sent: true };
    }

    case "reply": {
      const msgId = Number(args.id);
      const replyType = args.all ? "replyToAll" : "replyToSender";
      const details = {};
      if (args.html) {
        details.isPlainText = false;
        details.body = args.body;
      } else {
        details.isPlainText = true;
        details.plainTextBody = args.body;
      }
      const tab = await browser.compose.beginReply(msgId, replyType, details);
      await browser.compose.sendMessage(tab.id, { mode: "sendNow" });
      return { replied: true };
    }

    case "forward": {
      const details = {
        to: Array.isArray(args.to) ? args.to : [args.to],
      };
      const tab = await browser.compose.beginForward(Number(args.id), "forwardInline", details);
      await browser.compose.sendMessage(tab.id, { mode: "sendNow" });
      return { forwarded: true };
    }

    case "attachments": {
      const parts = await browser.messages.listAttachments(Number(args.id));
      return parts.map(p => ({
        partName: p.partName,
        name: p.name,
        contentType: p.contentType,
        size: p.size,
      }));
    }

    case "attachment": {
      const file = await browser.messages.getAttachmentFile(Number(args.id), args.partName);
      const buf = await file.arrayBuffer();
      const bytes = new Uint8Array(buf);
      let binary = "";
      for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
      return {
        name: file.name,
        contentType: file.type,
        data: btoa(binary),
      };
    }

    default:
      throw new Error(`Unknown command: ${command}`);
  }
}

// --- helpers ---

async function collectPages(pagePromise, limit) {
  const page = await pagePromise;
  let msgs = page.messages || [];
  let pageId = page.id;
  while (pageId && msgs.length < limit) {
    const next = await browser.messages.continueList(pageId);
    msgs = msgs.concat(next.messages || []);
    pageId = next.id;
  }
  return msgs.slice(0, limit);
}

async function getAllFolders(acct) {
  // Use rootFolder from accounts.list() — available in TB 121+
  const rootId = acct.rootFolder ? acct.rootFolder.id : acct.id;
  try {
    // getSubFolders with true = include entire subtree recursively
    const folders = await browser.folders.getSubFolders(rootId, true);
    return flattenWithSubFolders(folders);
  } catch (e) {
    // Fallback: try without recursive flag
    try {
      const folders = await browser.folders.getSubFolders(rootId);
      return folders || [];
    } catch (e2) {
      return [];
    }
  }
}

function flattenWithSubFolders(folders) {
  const result = [];
  for (const f of (folders || [])) {
    result.push(f);
    if (f.subFolders && f.subFolders.length) {
      result.push(...flattenWithSubFolders(f.subFolders));
    }
  }
  return result;
}

async function resolveFolder(spec) {
  const accounts = await browser.accounts.list();
  const lower = spec.toLowerCase();

  for (const acct of accounts) {
    const folders = await getAllFolders(acct);

    // Exact match on path or name (case-insensitive)
    for (const f of folders) {
      if (f.path === spec || f.name === spec) return f;
      if (f.path && f.path.toLowerCase() === lower) return f;
      if (f.name && f.name.toLowerCase() === lower) return f;
      if (f.path && f.path.toLowerCase() === "/" + lower) return f;
    }

    // Match by specialUse (INBOX -> ["inbox"], SENT -> ["sent"], etc.)
    const useMap = {
      "inbox": "inbox", "sent": "sent", "drafts": "drafts",
      "trash": "trash", "junk": "junk", "archive": "archives",
      "templates": "templates",
    };
    const useKey = useMap[lower];
    if (useKey) {
      for (const f of folders) {
        if (f.specialUse && f.specialUse.includes(useKey)) return f;
      }
    }
  }

  // Build helpful error with available folder names
  const available = [];
  for (const acct of accounts) {
    const folders = await getAllFolders(acct);
    available.push(...folders.map(f => f.name));
  }
  throw new Error(`Folder not found: "${spec}". Available: ${available.join(", ")}`);
}

function summarizeMessage(m) {
  return {
    id: m.id,
    date: m.date ? new Date(m.date).toISOString() : null,
    from: m.author,
    to: m.recipients,
    subject: m.subject,
    read: m.read,
    flagged: m.flagged,
    tags: m.tags,
    size: m.size,
  };
}

function extractBody(fullMsg, format) {
  const parts = [];
  gatherParts(fullMsg, parts);
  if (format === "html") {
    const html = parts.find(p => p.contentType === "text/html");
    if (html) return html.body;
  }
  const plain = parts.find(p => p.contentType === "text/plain");
  if (plain) return plain.body;
  const html = parts.find(p => p.contentType === "text/html");
  if (html) return html.body;
  return "";
}

function gatherParts(part, result) {
  if (part.body) result.push(part);
  if (part.parts) part.parts.forEach(p => gatherParts(p, result));
}

// Connect on startup
connectNativeHost();
