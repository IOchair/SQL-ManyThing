# Unreal Header Tool (UHT) Generated Files Explained

## Overview

UHT is Unreal Engine's custom parsing and code generation tool, running before the C++ compiler in the build pipeline. It parses header files annotated with `UCLASS`, `UPROPERTY`, `UFUNCTION` and other macros, outputting boilerplate code used by the reflection system.

```
Source files (.h/.cpp)
      ↓
   [UHT Parsing]
      ↓
Generated .generated.h / .gen.cpp
      ↓
   [C++ Compiler]
      ↓
   Final binary
```

## Generated Files Overview

| File | Location | Description |
|------|----------|-------------|
| `{Name}.generated.h` | `Intermediate/.../UHT/` | Functions and macro expansions injected into the class declaration |
| `{Name}.gen.cpp` | `Intermediate/.../UHT/` | Provides function body implementations for the above declarations |
| `{Module}Classes.h` | Same path | Aggregates all class headers in the module (legacy) |
| `{Module}.generated.dep.h` | Same path | Records gen.cpp dependency order |

Generated at: `Intermediate/Build/{Platform}/UnrealEditor/Inc/{Project}/UHT/`

## .generated.h Content (SQL-ManyThing Enrich Data Source)

### GENERATED_BODY Macro Expansion

```cpp
UCLASS()
class AMyActor : public AActor {
    GENERATED_BODY()
};
```

UHT replaces it with:
```
{CURRENT_FILE_ID}_{LINE}_INCLASS_NO_PURE_DECLS   // In-class declarations
{CURRENT_FILE_ID}_{LINE}_ENHANCED_CONSTRUCTORS    // Enhanced constructors
```

### Core Injected Content

| Content | Pattern | Description |
|---------|---------|-------------|
| Reflection static function | `StaticClass()` declaration | Type information access entry point |
| UFUNCTION Thunk | `DECLARE_FUNCTION(execXxx)` | Blueprint VM bridge for BlueprintCallable functions |
| UPROPERTY accessor | `execGetHealth(...)` etc. | Blueprint property access trampoline (not the property declaration itself) |
| Network replication | `GetLifetimeReplicatedProps` | Properties marked Replicated (implementation only in gen.cpp) |
| Class metadata | `DECLARE_CLASS2(Name, Parent, ...)` | Class name, parent class, package path |

### UHT 4 Type Markers

| Type | Begin Marker | Key Macro | Characteristics |
|------|-------------|-----------|-----------------|
| UCLASS | `Begin Class Xxx` | `DECLARE_CLASS2(X, Parent, ...)` | Most complex, includes RPC/CALLBACK/INCLASS/ENHANCED sections |
| UINTERFACE | `Begin Interface Xxx` | `DECLARE_CLASS2(X, UInterface, ...)` + `INCLASS_IINTERFACE` | No DECLARE_FUNCTION |
| USTRUCT | `Begin ScriptStruct FAIStimulus` | `StaticStruct()` | Only contains GENERATED_BODY, no functions |
| UENUM | `Begin Enum EAISenseNotifyType` | `FOREACH_ENUM_`, `StaticEnum<>` | Contains complete enum value list |

## .gen.cpp Content (Only in Full Engine Build, Not in InstalledBuild)

### Type Information Registration
```cpp
static FCompiledInDefer Z_CompiledInDeferFile_{FileID}(
    Z_Construct_UClass_AMyActor,
    &AMyActor::StaticClass,
    TEXT("AMyActor"),
    ...
);
```

### FuncMap Population
```cpp
void AMyActor::StaticRegisterNatives() {
    UClass* Class = GetPrivateStaticClass();
    static const FNameNativePtrPair Funcs[] = {
        { "MyFunction", &execMyFunction },
    };
}
```
This is the **complete registry of all UFUNCTIONs (including BlueprintImplementableEvent)**.

### Property Descriptors
```cpp
static FIntProperty* NewProp_Health = new FIntProperty(
    Class, "Health", RF_Public|RF_Transient,
    STRUCT_OFFSET(AMyActor, Health), ...
);
```
Contains: offset, type, flags (EditAnywhere/BlueprintReadWrite, etc.).

### Z_Construct_UClass_* Function Body
Constructs the complete UClass object, including class name, parent class, function list, property list, and metadata.

### UFUNCTION Thunk Function Body
```cpp
DEFINE_FUNCTION(AMyActor::execMyFunction) {
    P_GET_PROPERTY(FIntProperty, Z_Param_Value);
    P_FINISH;
    P_NATIVE_BEGIN;
    P_THIS->MyFunction(Z_Param_Value);
    P_NATIVE_END;
}
```

## SQL-ManyThing Enrich Current Status

| Information Source | Extractable From | Current Status | Notes |
|--------------------|------------------|---------------|-------|
| UCLASS + parent class | `.generated.h` | ✅ Extracted | |
| UFUNCTION(BlueprintCallable) | `.generated.h` DECLARE_FUNCTION(exec*) | ✅ Extracted | Auto-strips `exec` prefix |
| UFUNCTION(BlueprintImplementableEvent) | `.generated.h` CALLBACK_WRAPPERS | ❌ Not extracted | No DECLARE_FUNCTION macro |
| UINTERFACE | `.generated.h` `Begin Interface` | ✅ Extracted | parent = UInterface |
| USTRUCT | `.generated.h` `Begin ScriptStruct` | ✅ Extracted | |
| UENUM + values | `.generated.h` `Begin Enum` + FOREACH_ENUM_ | ✅ Extracted | Includes complete enum value list |
| UPROPERTY list + types | `.gen.cpp` NewProp_* | ❌ Unavailable | InstalledBuild has no .gen.cpp |
| Exact module name | DECLARE_CLASS2 TEXT("/Script/...") | ✅ Extracted | No longer guessed from directory name |

## Notes

- UHT is a dumb parser; it does not process C++ preprocessor directives like `#ifdef`. Macro annotations must be directly visible
- `Intermediate/` generated files should not be committed to version control; they are regenerated automatically on each build
- `.generated.h` must be the last `#include` in the header file, otherwise compilation will error
- **InstalledBuild (precompiled engine) only has .generated.h, no .gen.cpp** — UPROPERTY metadata cannot be obtained from UHT artifacts

## Query template: finding UHT-enriched symbols

```sql
-- All classes in a module
SELECT f.path, json_extract(s.value, '$.name') AS class_name
FROM files f
JOIN file_enrich e ON f.id = e.file_id,
     json_each(e.symbols) AS s
WHERE f.path LIKE 'Source/Runtime/Engine/%'
  AND json_extract(s.value, '$.kind') = 'class'
LIMIT 30;

-- Functions in a specific UHT class
SELECT json_extract(s.value, '$.name') AS name,
       json_extract(s.value, '$.kind') AS kind,
       json_array_length(json_extract(s.value, '$.uht_functions')) AS fn_count
FROM files f
JOIN file_enrich e ON f.id = e.file_id,
     json_each(e.symbols) AS s
WHERE f.path LIKE '%Actor.h'
  AND json_extract(s.value, '$.name') LIKE '%Actor'
  AND json_extract(s.value, '$.kind') = 'class';

-- UENUM values
SELECT f.path, json_extract(s.value, '$.name') AS enum_name
FROM files f
JOIN file_enrich e ON f.id = e.file_id,
     json_each(e.symbols) AS s
WHERE json_extract(s.value, '$.kind') = 'enum'
LIMIT 20;
```
