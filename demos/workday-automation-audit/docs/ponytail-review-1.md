# Ponytail review, round 1

Scope: `src/workday_audit`, `config`, `tests`, the n8n builder, the guide templates.

## Must fix

1. **The sheet node was in front of the Gmail draft.** n8n replaces the item with the sheet response, so the draft would have been saved empty. *Fixed:* Map fields connects to the sheet and the draft in parallel. The draft, the sheet columns, and the disabled send node all read `$('Map fields')`.

2. **A UK postcode was only partly removed, and "Dr" was treated as a street.** `4 River Court, Bristol BS1 4ST` left `1 4ST` in the text. `Dr. Lena Cho` was split because the address rule treated Dr as Drive. *Fixed:* street words have to look like a name (so "concerns Dr" is not an address), and the postcode is part of the address span. Python and the generated JavaScript agree on the 65-item corpus.

3. **Some work sentences vanished.** "2 hrs", "takes 20mins" on the next line, and "10 minutes and 3 hours" were neither tasks nor questions. "not a weekly task" was scored as weekly. *Fixed:* `hrs` counts, a following "takes N" line attaches, a factor-of-three gap is a question, "and" splits only when both sides are their own tasks, and "not" / "never" immediately before a repeat word cancels that word.

## Should fix

4. **The score on the row did not equal the formula applied to the rounded fields on that same row** (off by one in the sixth decimal). *Fixed:* hours and hours-saved are rounded before the score is stored.

5. **A question mark in the middle of a voice note split the sentence.** *Fixed:* clauses split on periods and exclamation marks, not on question marks.

6. **`(503) 555-0148` left the opening parenthesis behind**, so a later phone check could still see a fragment. *Fixed:* the phone rule includes the parentheses.

## Nice to have (not done)

- "Every other Friday" is a question. A biweekly rate would be a guess, so it stays a question.
- A single first name with no "Dear" or "Hi" and no surname is not redacted.
- The n8n HTTP response path is defensive (`body`, `data`, `content`) and still untested against a live n8n.

Verdict: fixes applied. See round 2.
