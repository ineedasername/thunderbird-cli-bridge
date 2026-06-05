# Thunderbird WebExtension API Reference (MV3, TB 128+)

Practical reference for the messages, folders, accounts, and compose APIs.

Sources: [messages API](https://webextension-api.thunderbird.net/en/latest/messages.html) | [folders API](https://webextension-api.thunderbird.net/en/latest/folders.html) | [accounts API](https://webextension-api.thunderbird.net/en/latest/accounts.html) | [compose API](https://webextension-api.thunderbird.net/en/latest/compose.html) | [message lists guide](https://webextension-api.thunderbird.net/en/latest/guides/messageLists.html)

---

## Key Types

### MailFolderId

A **string**. Unique identifier for a folder within a session. Renaming or moving a folder invalidates its id. Obtain these from `accounts.list()` or `folders.getSubFolders()` -- never construct them manually.

### MessageId

An **integer**. Internal tracking number for a message. Does not persist across restarts. Does not follow a message moved to a different folder. Not the same as the `Message-ID` email header (that is `headerMessageId`).

### MailAccountId

A **string**. Unique identifier for a mail account.

---

## MessageHeader

Returned by `messages.get()`, and in arrays inside `MessageList`.

```typescript
{
  id:               MessageId,        // integer, internal tracking number
  date:             Date,             // send timestamp from Date header
  author:           string,           // "Name <email>" format
  recipients:       string[],         // To: addresses (not populated for NNTP)
  ccList:           string[],         // Cc: addresses (not populated for NNTP)
  bccList:          string[],         // Bcc: addresses (not populated for NNTP)
  subject:          string,
  size:             integer,          // total size in bytes
  headerMessageId:  string,           // the Message-ID email header value
  flagged:          boolean,          // starred
  read:             boolean,          // (optional, requires accountsRead permission)
  junk:             boolean,          // junk classification
  junkScore:        integer,          // 0-100 junk score
  new:              boolean,          // recently received
  headersOnly:      boolean,          // only headers downloaded
  external:         boolean,          // external/file-based message
  priority:         string,           // "highest"|"high"|"normal"|"low"|"lowest"|"none"
  tags:             string[],         // custom tag keys
  folder:           MailFolder,       // (optional, requires accountsRead permission)
}
```

### MessageList

Paginated result returned by `messages.list()` and `messages.query()`.

```typescript
{
  id:       string | null,      // null if no more pages; pass to continueList()
  messages: MessageHeader[],    // current page (default ~100 messages per page)
}
```

### MessageAttachment

Returned by `messages.listAttachments()`.

```typescript
{
  contentType:        string,         // MIME type ("text/x-moz-deleted" = deleted)
  contentDisposition: string,         // "attachment" or "inline"
  name:               string,         // display name / filename
  partName:           string,         // MIME part identifier (e.g. "1.2")
  size:               integer,        // bytes
  contentId:          string,         // (optional) for inline/related parts
  message:            MessageHeader,  // (optional) if attachment is an .eml
  headers:            object,         // RFC 2047 decoded attachment headers
}
```

### MailFolder

```typescript
{
  id:          MailFolderId,  // string
  name:        string,        // human-friendly name
  path:        string,        // path within the account
  accountId:   MailAccountId, // (optional, not for unified/tag folders)
  isFavorite:  boolean,
  isRoot:      boolean,
  isVirtual:   boolean,       // virtual search folder
  isTag:       boolean,       // virtual tag folder
  isUnified:   boolean,       // unified mailbox folder
  specialUse:  string[],      // ["inbox"], ["sent"], ["drafts"], ["trash"], ["junk"],
                              // ["templates"], ["archives"], ["outbox"]
  subFolders:  MailFolder[],  // (optional, only if requested)
}
```

### MailAccount

```typescript
{
  id:          MailAccountId,   // string
  name:        string,          // display name
  type:        string,          // "imap"|"pop3"|"local"|"nntp"|"rss"|"ews"
  identities:  MailIdentity[],  // default identity first
  rootFolder:  MailFolder,      // root folder (added TB 121)
}
```

---

## 1. messages.list()

```typescript
browser.messages.list(
  folderId: MailFolderId,     // STRING, not a MailFolder object
  options?: {
    sortType?: string,        // sort field
    sortOrder?: string,       // sort direction
  }
): Promise<MessageList>
```

**The key point**: `messages.list()` takes a **`MailFolderId` string**, not a `MailFolder` object. Get the id from `folder.id`.

**Permission required**: `messagesRead`

```javascript
// Example: list messages in a folder
let accounts = await browser.accounts.list();
let rootFolder = accounts[0].rootFolder;
let subFolders = await browser.folders.getSubFolders(rootFolder.id);
let inbox = subFolders.find(f => f.specialUse.includes("inbox"));

let page = await browser.messages.list(inbox.id);
// page.messages is MessageHeader[]
// page.id is string|null for pagination
```

### Pagination

```javascript
let page = await browser.messages.list(folderId);
let allMessages = [...page.messages];

while (page.id) {
  page = await browser.messages.continueList(page.id);
  allMessages.push(...page.messages);
}
```

Or with an async generator:

```javascript
async function* iterateMessages(listPromise) {
  let page = await listPromise;
  for (let msg of page.messages) yield msg;
  while (page.id) {
    page = await browser.messages.continueList(page.id);
    for (let msg of page.messages) yield msg;
  }
}

for await (let msg of iterateMessages(browser.messages.list(folderId))) {
  console.log(msg.subject);
}
```

---

## 2. messages.get() and messages.getFull()

```typescript
browser.messages.get(
  messageId: MessageId       // integer
): Promise<MessageHeader>

browser.messages.getFull(
  messageId: MessageId,      // integer
  options?: {
    decodeContent?: boolean,
    decodeHeaders?: boolean,
    decrypt?: boolean,
  }
): Promise<MessagePart>
```

`get()` returns a `MessageHeader`. `getFull()` returns the full MIME tree as a `MessagePart`:

```typescript
// MessagePart (recursive)
{
  body?:        string,
  contentType?: string,
  headers?:     object,        // { "content-type": ["..."], ... }
  name?:        string,
  partName?:    string,
  parts?:       MessagePart[], // child parts (multipart)
  size?:        integer,
}
```

```javascript
let header = await browser.messages.get(12345);
let full = await browser.messages.getFull(12345, { decodeContent: true });
// full.parts[0].parts[0].body contains the text
```

---

## 3. messages.query()

```typescript
browser.messages.query(
  queryInfo?: {
    accountId?:          MailAccountId,
    folderId?:           MailFolderId,
    includeSubFolders?:  boolean,
    author?:             string,
    recipients?:         string,
    subject?:            string,
    body?:               string,
    fullText?:           string,
    fromDate?:           Date,
    toDate?:             Date,
    flagged?:            boolean,
    read?:               boolean,
    junk?:               boolean,
    attachment?:         boolean,
    headerMessageId?:    string,
    tags?:               TagsDetail,
    fromMe?:             boolean,
    toMe?:               boolean,
    new?:                boolean,
    size?:               integer,
    online?:             boolean,
    messagesPerPage?:    integer,
    returnMessageListId?: boolean,
  }
): Promise<MessageList | string>
```

If `returnMessageListId` is true, returns a string (messageListId) instead of a `MessageList`.

```javascript
// Find unread messages from a specific author
let results = await browser.messages.query({
  folderId: inboxId,
  author: "alice@example.com",
  read: false,
});

for (let msg of results.messages) {
  console.log(msg.subject, msg.date);
}
```

---

## 4. messages.move(), messages.delete(), messages.update()

```typescript
browser.messages.move(
  messageIds: MessageId[],    // array of integers
  folderId: MailFolderId,     // destination folder (string)
  options?: { isUserAction?: boolean }
): Promise<void>

browser.messages.delete(
  messageIds: MessageId[],    // array of integers
  options?: {
    deletePermanently?: boolean,  // skip trash
    isUserAction?: boolean,
  }
): Promise<void>

browser.messages.update(
  messageId: MessageId,       // single integer (not array)
  newProperties: {
    flagged?: boolean,
    junk?: boolean,
    read?: boolean,
    tags?: string[],
  }
): Promise<void>
```

**Permission required**: `messagesMove` for move, `messagesDelete` for delete, `messagesUpdate` (or `messagesRead`) for update.

```javascript
// Move messages to trash
await browser.messages.move([msg.id], trashFolder.id);

// Permanently delete
await browser.messages.delete([msg.id], { deletePermanently: true });

// Mark as read and flagged
await browser.messages.update(msg.id, { read: true, flagged: true });
```

---

## 5. folders.getSubFolders()

```typescript
browser.folders.getSubFolders(
  folderId: MailFolderId,           // string
  includeSubFolders?: boolean       // recursively include nested subfolders (default false)
): Promise<MailFolder[]>
```

**Permission required**: `accountsRead`

```javascript
let accounts = await browser.accounts.list();
let rootId = accounts[0].rootFolder.id;

// Get direct children only
let folders = await browser.folders.getSubFolders(rootId);

// Get entire tree recursively
let allFolders = await browser.folders.getSubFolders(rootId, true);
// Each folder's .subFolders will be populated
```

---

## 6. accounts.list()

```typescript
browser.accounts.list(
  includeSubFolders?: boolean   // populate rootFolder.subFolders tree (default false)
): Promise<MailAccount[]>
```

**Permission required**: `accountsRead`

```javascript
let accounts = await browser.accounts.list(true);
for (let acct of accounts) {
  console.log(acct.id, acct.name, acct.type);
  // acct.rootFolder.subFolders is populated because we passed true
  for (let folder of acct.rootFolder.subFolders) {
    console.log("  ", folder.name, folder.specialUse, folder.id);
  }
}
```

---

## 7. Compose API

```typescript
browser.compose.beginNew(
  messageId?: MessageId,           // template/message to base on (optional)
  details?: ComposeDetails
): Promise<Tab>

browser.compose.beginReply(
  messageId: MessageId,
  replyType?: "replyToSender" | "replyToAll" | "replyToList",
  details?: ComposeDetails
): Promise<Tab>

browser.compose.beginForward(
  messageId: MessageId,
  forwardType?: "forwardInline" | "forwardAsAttachment",
  details?: ComposeDetails
): Promise<Tab>

browser.compose.sendMessage(
  tabId: integer,                  // compose tab id from beginNew/etc
  options?: {
    mode?: "default" | "sendNow" | "sendLater",
  }
): Promise<{
  messages: MessageHeader[],
  mode: string,
  headerMessageId?: string,
  error?: string,
}>
```

**Permission required**: `compose` for begin*, `compose.send` for sendMessage.

### ComposeDetails (key properties)

```typescript
{
  to?:             string[] | ComposeRecipient[],
  cc?:             string[] | ComposeRecipient[],
  bcc?:            string[] | ComposeRecipient[],
  from?:           string,           // override sender
  subject?:        string,
  body?:           string,           // HTML body
  plainTextBody?:  string,           // plain text body
  isPlainText?:    boolean,
  identityId?:     string,           // which identity to send from
  attachments?:    ComposeAttachment[],
}
```

```javascript
// Compose a new message
let tab = await browser.compose.beginNew(null, {
  to: ["bob@example.com"],
  subject: "Hello",
  plainTextBody: "Hi Bob!",
  isPlainText: true,
});

// Send it
let result = await browser.compose.sendMessage(tab.id, { mode: "sendNow" });

// Reply to a message
let replyTab = await browser.compose.beginReply(msg.id, "replyToSender", {
  plainTextBody: "Thanks for your message!",
});
```

---

## 8. messages.listAttachments() and messages.getAttachmentFile()

```typescript
browser.messages.listAttachments(
  messageId: MessageId
): Promise<MessageAttachment[]>

browser.messages.getAttachmentFile(
  messageId: MessageId,
  partName: string              // from MessageAttachment.partName
): Promise<File>
```

**Permission required**: `messagesRead`

```javascript
let attachments = await browser.messages.listAttachments(msg.id);
for (let att of attachments) {
  console.log(att.name, att.contentType, att.size);

  let file = await browser.messages.getAttachmentFile(msg.id, att.partName);
  // file is a standard File object
  let arrayBuffer = await file.arrayBuffer();
  let text = await file.text(); // if text-based
}
```

---

## Required Permissions Summary

| Permission       | APIs                                          |
|------------------|-----------------------------------------------|
| `accountsRead`   | accounts.list, folders.getSubFolders          |
| `messagesRead`   | messages.list, get, getFull, query, listAttachments, getAttachmentFile |
| `messagesMove`   | messages.move                                 |
| `messagesDelete` | messages.delete                               |
| `messagesUpdate` | messages.update (also works with messagesRead in some versions) |
| `compose`        | compose.beginNew, beginReply, beginForward    |
| `compose.send`   | compose.sendMessage                           |

## manifest.json permissions example

```json
{
  "permissions": [
    "accountsRead",
    "messagesRead",
    "messagesMove",
    "messagesDelete",
    "compose",
    "compose.send"
  ]
}
```
