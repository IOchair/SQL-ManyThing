# UE GAS AttributeSet Analysis via SQL-ManyThing

Analyze a specific `UAttributeSet` subclass in the UE Engine index: class specifiers, attribute types, replication setup, and Blueprint initialization readiness.

## When to Use

- User asks about a specific `UAttributeSet` in UE source
- Need to diagnose BP init failure, replication issues, or modifier pipeline behavior
- Comparing test vs production attribute sets

## Probe Sequence

### 1. Locate the file pair

Find both `.h` (declaration) and `.cpp` (implementation):

```sql
SELECT path FROM files
WHERE path LIKE '%.h' AND content LIKE '%<AttributeSetName>%'
  AND path NOT LIKE '%Generated%'
  AND path GLOB '*GameplayAbilities*'
LIMIT 5;
```

Or use FTS5:

```sql
SELECT path, rank FROM files_fts
WHERE files_fts MATCH '<AttributeSetName>'
  AND path LIKE '%.h'
ORDER BY rank
LIMIT 5;
```

### 2. Extract class definition with UCLASS macro

Find the header offset:

```sql
SELECT instr(content, 'UCLASS(') AS uclass_offset,
       instr(content, 'class <AttributeSetName>') AS class_offset
FROM files WHERE path = '... .h';
```

Then extract a bounded window around UCLASS → first closing brace. Usually 3000-5000 chars covers a full class body.

Check specifically:

```
UCLASS() specifiers present?
  - BlueprintType?        → BP can use as type
  - Blueprintable?        → BP can subclass
  - HideInDetailsView?    → hidden from Editor UI
  - DefaultToInstanced?   → required for runtime init
```

### 3. Check attribute type — `FGameplayAttributeData` vs raw `float`

Scan UPROPERTY declarations in the class body. Categorize:

| Type | GAS Pipeline Support | BP Init | Replication |
|---|---|---|---|
| `FGameplayAttributeData` | Full: base/current separation, modifiers, OnRep | Via `InitFromMetaData()` | Built-in broadcast |
| raw `float` | Partial: no base/current split, `GetGameplayAttributeData()` returns nullptr | CDO set works but system can't distinguish base from modified | Manual DOREPLIFETIME only |

Heuristic: search for `FGameplayAttributeData` in the header:

```sql
SELECT instr(content, 'FGameplayAttributeData') AS gad_offset
FROM files WHERE path = '... .h';
```

If `0` — no attributes use the proper GAS wrapper. This is the root cause of most BP init issues.

### 4. Check `mutable` keyword

```sql
SELECT instr(content, 'mutable') AS mutable_offset
FROM files WHERE path = '... .h';
```

`mutable` on all attributes = test-only pattern. Comment in `AbilitySystemTestAttributeSet` says: "Mutable is not required and should never be used on normal attribute sets."

`mutable` conflicts with BP CDO const-correctness in some engine builds — BP compiler may skip these properties.

### 5. Check replication setup

Extract `GetLifetimeReplicatedProps` from the `.cpp`:

```sql
SELECT instr(content, 'GetLifetimeReplicatedProps') AS repl_offset
FROM files WHERE path = '... .cpp';
```

Then extract a bounded window (500-1000 chars). Look for:

- `DISABLE_ALL_CLASS_REPLICATED_PROPERTIES` — blocks all replication, used in test sets
- `DOREPLIFETIME(...)` — active replication per attribute; should be present for every `Replicated` property
- Commented-out DOREPLIFETIME lines — all replication intentionally disabled

### 6. Check modifier pipeline metadata

Scan each UPROPERTY's `meta=` for:

- `HideFromModifiers` → GameplayEffect can't modify this attribute
- `GameplayEffectExecute` → attribute participates in execute callbacks

## BP Init Readiness Checklist

Verify against this list. Missing items = root cause:

- [ ] UCLASS has `BlueprintType` and `Blueprintable`
- [ ] All attributes use `FGameplayAttributeData` (not raw `float`)
- [ ] No `mutable` on attribute declarations
- [ ] Active `DOREPLIFETIME(...)` entries for each `Replicated` property
- [ ] No `DISABLE_ALL_CLASS_REPLICATED_PROPERTIES`
- [ ] Constructor properly initializes all `FGameplayAttributeData` via `SetBaseValue()`
- [ ] No `HideFromModifiers` unless intentional
- [ ] No `HideInDetailsView` on UCLASS (or user knows how to bypass)

## Example: `AbilitySystemTestAttributeSet` Diagnosis

| Check | Result | Root cause? |
|---|---|---|
| BlueprintType + Blueprintable | ✅ Present | No |
| `FGameplayAttributeData` used | ❌ Only Mana; rest are raw `float` | **Yes — primary** |
| No `mutable` | ❌ All attributes use `mutable` | Supporting — BP CDO conflicts |
| Active DOREPLIFETIME | ❌ `DISABLE_ALL_CLASS_REPLICATED_PROPERTIES` + all DOREPLIFETIME commented out | Supporting — no replication |
| HideFromModifiers | ❌ MaxHealth, Health have it | Minor — only 2 attrs affected |

**Primary fix**: Replace `mutable float` → `FGameplayAttributeData` on all attributes.
