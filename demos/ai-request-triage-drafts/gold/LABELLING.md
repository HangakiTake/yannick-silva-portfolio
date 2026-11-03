# Labelling rules

These rules were written before the extractor. `labels.json` applies them to every sample. The extractor is not allowed to read this file or `labels.json`.

The business in the samples is fictional: Linden Home Services, a small home-services company. Every person, company and address uses example.com, example.net, example.org or example.fr. Phone numbers use the 555 exchange, or an obviously fake French mobile.

## What is "the request"

Fields may only be taken from the customer's new text, the Subject, the From and Reply-To headers, and, for the web form, the form columns. For an email that is the text before any of these:

- a line starting with `>`
- `---------- Forwarded message ---------`
- `-----Original Message-----`
- `Begin forwarded message`
- `On ... wrote:` / `Le ... a écrit` / `Em ... escreveu` / `El ... escribió`
- a signature separator line `--`
- a confidentiality disclaimer ("This message and any attachments are confidential")

HTML that is `display:none`, `visibility:hidden`, or inside `script` or `style` is not part of the request.

If the new text has fewer than 20 letters and no request keyword (quote, book, invoice, help, devis, reserva, and the same list the samples use), the first forwarded block is the request instead. Header lines inside that block (From, To, Date, Sent, Subject, Cc) are not fields.

The email's Date header and a form's `submitted_at` are not key dates.

## Request type

One primary ask:

| Type | When |
|---|---|
| complaint | dissatisfaction, damage, a threat, or an angry complaint, including when they also mention money |
| billing | invoice, receipt, or a payment dispute that is not also a legal threat or an angry complaint |
| quote | they ask the price, or they describe a new job and do not name a slot ("need a handyman") |
| booking | they ask to reserve, schedule, or confirm a visit |
| support | help with a visit that already happened or an access problem (lockbox, "send someone back", reschedule) |
| other | spam, empty, a job application, a sales pitch, or anything that is not one of the above |

Quote words outrank booking words when both are present. Complaint outranks quote, booking, billing and support. A job pitch ("job", "hiring", "my experience") is other, even if it says "cleaner".

Spam cues (seo, backlink, crypto, bitcoin, lottery, casino, viagra, unsubscribe, "click here to claim", "limited offer") make the type other when the message has no customer-service ask.

## Urgency

- high: the message is a complaint with an angry or legal flag, a payment dispute, or it says urgent, asap, emergency, immediately, or "right now"
- low: no rush, whenever, no hurry, pas pressé, sin prisa, sem pressa
- normal: everything else

## Fields

- **customer_name.** A two-word name the person gives ("I am", "Je m'appelle", "Meu nome é", "Me llamo", "Soy", "this is") wins. Otherwise the From display name, if it looks like a person. A one-word display name, or a name whose words are all generic (office, team, info, admin, sales, noreply, accounts, support, desk, prize, seo, notification), is ignored. If From is generic and Reply-To has a person-like name, use the Reply-To name. Never invent a name from the mailbox local-part. Never take a name that appears only in quoted text.
- **company.** "at {Company}" in the new text, or the form's company column, or the first signature line that is not a greeting and not a job title (manager, director, directrice, directeur, owner). Never infer a company from the email domain.
- **contact_email.** An address the new text names ("send it to", "email", "e-mail") wins. Otherwise Reply-To, otherwise From. The form's email column is the contact email.
- **contact_phone.** The first phone in the new text or the kept signature, else the form's phone column. 10 or 11 digits. The business's own number, 503-555-0100, is never the customer's phone. Quoted numbers are ignored.
- **key_dates.** Calendar dates the customer states in the new text, the subject, or the form's preferred_date. Not the Date header, not submitted_at, not "today", "tomorrow", "Tuesday", or "autumn". Month names in English, French, Portuguese and Spanish count. Numeric dates are month/day/year. A numeric date is ambiguous when both month/day and day/month are real dates; those are still recorded, and the request must be flagged for a person. Store ISO dates (YYYY-MM-DD).
- **amounts.** Money the customer states about the job, the invoice, or a charge. A `$` or the word dollars or USD is required, so an invoice number is not money. Spam bait ("winnings of $50000") is not an amount. Quoted staff prices are not amounts. Do not compute a total. Canonical form: `$186.00` when the source has cents, otherwise `$186`.

## Needs a person

`expect_needs_human` is true when any of these hold:

- type is complaint or other
- urgency is high
- a flag is legal, payment_dispute, angry, spam, empty, or low_confidence

Flags:

- legal: attorney, lawyer, sue, lawsuit, court, avocat, abogado, advogado
- payment_dispute: charged twice, double charge, chargeback, dispute the charge, unauthorized charge, cobraron dos veces
- angry: furious, unacceptable, inaceptable, worst, disgusted, or a body that is mostly capitals
- spam: the spam cues above
- empty: fewer than 3 letters in the new text and in the subject (and an empty form message)
- low_confidence: empty or spam. A clear "other" (a job application, a sales pitch) is not low confidence; it still needs a person because the type is unknown.
