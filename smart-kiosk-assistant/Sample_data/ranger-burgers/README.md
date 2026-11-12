# Ranger Burgers test utterances

`na_intents.jsonl` holds 1,051 text utterances for the Ranger Burgers sample
menu (`configs/menus/ranger-burgers/`). Use it to check ordering and
question answering after you switch the kiosk to that menu. See
[Menu Selection](../../docs/user-guide/get-started/configuration.md) for how to
switch.

Each line is one JSON object and one customer turn. The texts are unique.

| Kind | Rows | What is checked |
| --- | --- | --- |
| `order` | 670 | The cart after the turn equals `expect_cart` |
| `question` | 331 | The reply matches at least `min_facts` of `expect_facts` and none of `forbid` |
| `not_on_menu` | 50 | Same as `question`: the reply says the item is not available |

## Fields

| Field | Present on | Meaning |
| --- | --- | --- |
| `id` | all | Row id. The letter prefix groups the category, for example `S` for `single` |
| `category` | all | Utterance type, listed below |
| `family` | all | Phrasing template, for example `i_d_like`, `can_i_get`, `how_much_is` |
| `kind` | all | `order`, `question` or `not_on_menu` |
| `text` | all | What the customer says |
| `seed` | some `order` rows | Cart contents before the turn, as `{product name: quantity}` |
| `expect_cart` | `order` rows | Full cart after the turn, as `{product name: quantity}` |
| `expect_facts` | `question`, `not_on_menu` | Case-insensitive regular expressions |
| `min_facts` | `question`, `not_on_menu` | How many `expect_facts` must match |
| `forbid` | `question`, `not_on_menu` | Regular expressions that must not match |
| `item` | some rows | Menu product the row is about |
| `alias` | some rows | Alias used in `text` instead of the menu name |
| `qty_form`, `size_style`, `meal_style`, `filler_pos`, `default_size_alias`, `expect` | some rows | Tags for slicing results |

Order categories: `single`, `single_alias`, `quantity`, `sized`, `meal`,
`two_items`, `three_items`, `change_remove`, `filler`.

Question categories: `price`, `ingredients`, `dietary`, `allergen`,
`calories`, `hours`, `store_info`, `category`, `recommend`, `combo_info`.

Every product name in `seed` and `expect_cart` matches a `name` in
`configs/menus/ranger-burgers/ordering/products.yaml` exactly.
`tests/functional/test_menu_ranger_burgers.py` checks this. Every
`expect_facts` set has at least `min_facts` matches in
`knowledge-base-samples/RangerBurgers-QSR-menu.md`.

Rows that use an alias (`single_alias`, and any row with an `alias` field)
are expected to fail until kiosk-core resolves product aliases.

Example rows:

```json
{"id": "S001", "category": "single", "family": "i_d_like", "kind": "order", "text": "I'd like one Banana Split Shake, please.", "expect_cart": {"Banana Split Shake": 1}}
{"id": "C001", "category": "change_remove", "family": "remove", "kind": "order", "text": "Can you remove the small coffee?", "seed": {"Blaze Chicken Sandwich": 1, "Coffee, Small": 1}, "expect_cart": {"Blaze Chicken Sandwich": 1}}
```
