#!/usr/bin/env python3
"""The ppc64le port's edits to files it shares with the other targets.

Authored here as readable text and emitted as a portedit table. Each entry is
(kind, path, anchor, payload); see portedit.py for what the kinds mean and for
the guarantees (idempotent, anchor must be unique, nothing written on doubt).

Edits live here rather than in a diff because an anchor survives upstream
churn and a line number does not. Where upstream has since done the same thing
itself, the entry is deleted and a note says so, so the port keeps shrinking
instead of carrying history forward.
"""

J = 'Source/JavaScriptCore/'
W = 'Source/WTF/wtf/'

EDITS = [

# --- assembler/CPU.h ------------------------------------------------------
('AFTER', J + 'assembler/CPU.h', '''constexpr bool isRISCV64()
{
#if CPU(RISCV64)
    return true;
#else
    return false;
#endif
}''', '''
constexpr bool isPPC64()
{
#if CPU(PPC64LE)
    return true;
#else
    return false;
#endif
}'''),

('REPLACE', J + 'assembler/CPU.h',
 '#elif CPU(ARM_THUMB2) || CPU(ARM64) || CPU(RISCV64)',
 '#elif CPU(ARM_THUMB2) || CPU(ARM64) || CPU(RISCV64) || CPU(PPC64LE)'),

# --- assembler/MaxFrameExtentForSlowPathCall.h ----------------------------
('AFTER', J + 'assembler/MaxFrameExtentForSlowPathCall.h',
 '''#elif CPU(ARM)
// First four args in registers, remaining 4 args on stack.
static constexpr size_t maxFrameExtentForSlowPathCall = 24;''',
 '''
#elif CPU(PPC64LE)
// All args are in registers on ELFv2 too, but a call still needs the 32-byte
// linkage area at the bottom of the CALLER's frame: back chain (0), CR (8),
// LR (16), TOC (24). The offlineasm PPC64 backend's `call` lowering writes
// r2 to 24(r1) and reloads it afterwards (jsc-ppc64le-port.md section 5.3),
// so that slot has to be reserved rather than overlapping JS frame data.
// 32 also satisfies the alignment assertion below:
// 32 % 16 == 0 == 16 - sizeof(CallerFrameAndPC) with a 16-byte CallerFrameAndPC.
static constexpr size_t maxFrameExtentForSlowPathCall = 32;'''),

# --- assembler/PerfLog.cpp ------------------------------------------------
('AFTER', J + 'assembler/PerfLog.cpp',
 'static constexpr uint32_t elfMachine = 0xF3;',
 '''#elif CPU(PPC64LE)
// EM_PPC64 = 21. The little-endian ABI does not get a separate e_machine.
static constexpr uint32_t elfMachine = 0x15;'''),

# --- b3/B3Common.cpp ------------------------------------------------------
('REPLACE', J + 'b3/B3Common.cpp',
 '    RELEASE_ASSERT(isARM64() || isRISCV64() || isARM_THUMB2());',
 '    RELEASE_ASSERT(isARM64() || isRISCV64() || isARM_THUMB2() || isPPC64());'),

('BEFORE', J + 'b3/B3Common.cpp', '''#elif CPU(X86_64)
    return GPRReg::InvalidGPRReg;''', '''#elif CPU(PPC64LE)
    // r0, and it is only usable because every consumer of this register now
    // builds an Arg::index rather than an Arg::addr. POWER's "r0 reads as
    // zero" is positional: in the RA field of a load, a store or addi the
    // encoding means the literal zero and the register is not consulted, so
    // `ld r3,0(0)` assembles and addresses absolute zero rather than faulting.
    // In the RB field of an X-form -- `ldx r3,r1,r0` -- and as a destination it
    // is an ordinary register. So r0 may be the offset but never the base, and
    // that is exactly the shape the three call sites were given. See
    // powerpc64le-handbook docs/jsc-ppc64le-extended-offset-reg.md.
    //
    // It is the only register that can serve. r1 is the stack pointer being
    // offset, r2 is the TOC that generated code may never write, r13 is the
    // ABI thread pointer and r31 is cfr; and the alternative -- reserving a
    // base-capable GPR -- costs one of the thirteen allocatable registers
    // permanently.
    return PPC64Registers::r0;'''),

# --- disassembler/CapstoneDisassembler.cpp --------------------------------
# Upstream grew an ARM_THUMB2 arm here after the port was written; it is kept
# exactly as upstream has it and the ppc64 arm is added beside it.
('AFTER', J + 'disassembler/CapstoneDisassembler.cpp',
 '''#elif CPU(ARM64)
    if (cs_open(CS_ARCH_ARM64, CS_MODE_ARM, &handle) != CS_ERR_OK)
        return false;''',
 '''#elif CPU(PPC64LE)
    // ppc64 little-endian. CS_MODE_LITTLE_ENDIAN is 0 and so is redundant, but
    // it is spelled out because it is not a no-op decision: PPCDisassembler.c
    // reads the instruction word through MODE_IS_BIG_ENDIAN(), so the wrong
    // choice does not fail, it decodes every word byte-reversed into some
    // other valid instruction. CS_MODE_64 selects the 64-bit forms. The
    // remaining PPC mode bits -- QPX, SPE, BOOKE, PS -- name instruction sets
    // this port does not emit and POWER9 does not implement, and each steals
    // encoding space from the VSX forms the port does emit, so none is set.
    if (cs_open(CS_ARCH_PPC, static_cast<cs_mode>(CS_MODE_64 | CS_MODE_LITTLE_ENDIAN), &handle) != CS_ERR_OK)
        return false;'''),

# cs_disasm() stops at the first word it cannot decode and reports how far it
# got, which silently truncates a JIT dump at the first unknown encoding --
# exactly the case the dump is being read to investigate.
('REPLACE', J + 'disassembler/CapstoneDisassembler.cpp',
 '''    size_t count = cs_disasm(handle, codePtr.dataLocation<unsigned char*>(), size, codePtr.dataLocation<uintptr_t>(), 0, &instructions);
    if (count > 0) {
        for (size_t i = 0; i < count; ++i) {
            auto& instruction = instructions[i];
            out.printf("%s%#16llx: %s %s", prefix, static_cast<unsigned long long>(instruction.address), instruction.mnemonic, instruction.op_str);
            if (auto str = AssemblyCommentRegistry::singleton().comment(reinterpret_cast<void *>(static_cast<uintptr_t>(instruction.address))))
                out.printf("; %s\\n", str->ascii().data());
            else
                out.printf("\\n");
        }
        cs_free(instructions, count);
    }
    cs_close(&handle);
    return true;''',
 '''    cs_insn* instruction = cs_malloc(handle);
    if (!instruction) {
        cs_close(&handle);
        return false;
    }

    auto printComment = [&](uintptr_t address) {
        if (auto str = AssemblyCommentRegistry::singleton().comment(reinterpret_cast<void*>(address)))
            out.printf("; %s\\n", str->ascii().data());
        else
            out.printf("\\n");
    };

    const uint8_t* cursor = codePtr.dataLocation<const uint8_t*>();
    uintptr_t address = codePtr.dataLocation<uintptr_t>();
    size_t remaining = size;

    // Iterate rather than calling cs_disasm() once: on a decode failure emit
    // the raw word and step over it instead of abandoning the rest of the
    // dump. Every target above is a fixed 4-byte instruction set, so resyncing
    // is an aligned step and cannot lose the instruction stream.
    constexpr size_t instructionWidth = 4;
    while (remaining) {
        if (cs_disasm_iter(handle, &cursor, &remaining, &address, instruction)) {
            out.printf("%s%#16llx: %s %s", prefix, static_cast<unsigned long long>(instruction->address), instruction->mnemonic, instruction->op_str);
            printComment(static_cast<uintptr_t>(instruction->address));
            continue;
        }

        size_t step = std::min(instructionWidth, remaining);
        uint32_t word = 0;
        memcpy(&word, cursor, step);
        out.printf("%s%#16llx: .long %#010x", prefix, static_cast<unsigned long long>(address), word);
        printComment(address);
        cursor += step;
        address += step;
        remaining -= step;
    }

    cs_free(instruction, 1);
    cs_close(&handle);
    return true;'''),

('REPLACE', J + 'disassembler/CapstoneDisassembler.cpp',
 '''#include <capstone/capstone.h>''',
 '''#include <capstone/capstone.h>
#include <algorithm>
#include <cstring>'''),

('REPLACE', J + 'disassembler/CapstoneDisassembler.cpp',
 '''    csh handle;
    cs_insn* instructions;''',
 '''    csh handle;'''),

# --- jit/ExecutableAllocator.cpp ------------------------------------------
('AFTER', J + 'jit/ExecutableAllocator.cpp',
 '''#elif CPU(X86_64)
static constexpr size_t fixedExecutableMemoryPoolSize = 1 * GB;''',
 '''#elif CPU(PPC64LE)
#if ENABLE(JUMP_ISLANDS)
// Without islands this had to be <= nearJumpRange (32 MB). With them it does
// not, and it should not stay at 32 MB: each region gives up islandRegionSize
// to island space, so a 32 MB pool would allocate only 28 MB. 128 MB of
// reserved (not committed) address space restores the headroom and then some.
static constexpr size_t fixedExecutableMemoryPoolSize = 128 * MB;
#else
static constexpr size_t fixedExecutableMemoryPoolSize = 32 * MB;
#endif'''),

('REPLACE', J + 'jit/ExecutableAllocator.cpp',
 '''#if CPU(ARM64)
static constexpr double islandRegionSizeFraction = 0.125;
static constexpr size_t islandSizeInBytes = 4;''',
 '''#if CPU(ARM64) || CPU(PPC64LE)
// An island is one unconditional branch: `b` on both targets, 4 bytes on
// both. The region fraction is ARM64's; on PPC64 it makes each island region
// 4 MB of a 32 MB nearJumpRange, which is 1,048,576 islands per region.
static constexpr double islandRegionSizeFraction = 0.125;
static constexpr size_t islandSizeInBytes = 4;'''),

# --- jit/OperationResult.h ------------------------------------------------
('REPLACE', J + 'jit/OperationResult.h',
 '#if CPU(ARM64) || CPU(ARM_THUMB2)',
 '#if CPU(ARM64) || CPU(ARM_THUMB2) || CPU(PPC64LE)'),

('REPLACE', J + 'jit/OperationResult.h',
 '    && !std::is_floating_point_v<T> // The ARM64 ABI says that this should be returned in x0 instead of d0. Seems unlikely it\'s worth it to do the extra fmov.',
 '''    // The one place SysV x86-64 and another ABI classify
    // ExceptionOperationResult<T> differently. Enumerated for ELFv2 rather
    // than assumed, over every JSC_DECLARE[_NOEXCEPT]_JIT_OPERATION in the
    // tree -- 37 distinct return types:
    //
    //   * every scalar integer, pointer and enum T (EncodedJSValue, JSCell*,
    //     UCPUStrictInt32, size_t, bool, ...) makes a 16-byte
    //     {T, Exception*} whose eightbytes are both INTEGER. SysV returns it
    //     in rax:rdx, ELFv2 in r3:r4; both put the exception in
    //     returnValueGPR2, which is what operationExceptionRegister returns.
    //   * ExceptionOperationResult<void> is a lone Exception*: r3 / rax.
    //   * UGPRPair and ThrownExceptionInfo are 16 bytes, so the concept
    //     rejects them and they are returned bare: r3:r4 on ELFv2, rax:rdx
    //     on SysV, no float members in either.
    //   * float and double are the divergence, and are what this arm excludes.
    //
    // Nothing in the tree returns a homogeneous floating-point aggregate
    // (a struct of one or two floats). That is the remaining shape that would
    // diverge -- ELFv2 returns {struct{float,float}, Exception*} in GPRs while
    // SysV classifies the first eightbyte SSE -- but it would put the
    // exception in rax on x86-64 too, where the code asks for rdx, so it is
    // upstream-broken before it is port-broken.
    //
    // ARM64: the ABI says this should be returned in x0 instead of d0. Seems
    // unlikely it's worth it to do the extra fmov.
    // PPC64LE: ELFv2 returns the {float, Exception*} aggregate in r3:r4, not
    // in f1, and operationExceptionRegister assumes SysV's xmm0 + rax.
    // Excluded here so a float-returning operation returns a bare float in f1,
    // which the callOperation overload in MacroAssemblerPPC64.h converts into
    // the port's float register model. See jsc-ppc64le-yarr-wasm.md 7.3.
    && !std::is_floating_point_v<T>'''),

# --- wasm/WasmAddressType.h -----------------------------------------------
('REPLACE', J + 'wasm/WasmAddressType.h',
 '#if !PLATFORM(PLAYSTATION) && ENABLE(JIT)',
 '#if !PLATFORM(PLAYSTATION) && ENABLE(B3_JIT)'),

# --- wasm/WasmCallee.cpp --------------------------------------------------
('REPLACE', J + 'wasm/WasmCallee.cpp',
 '#if CPU(X86_64) || CPU(ARM64) || CPU(RISCV64)',
 '#if CPU(X86_64) || CPU(ARM64) || CPU(RISCV64) || CPU(PPC64LE)'),

# --- wasm/WasmOperations.cpp ----------------------------------------------
('AFTER', J + 'wasm/WasmOperations.cpp',
 '''    context.gpr(RISCV64Registers::ra) = std::bit_cast<UCPURegister>(*(framePointer + 1));
    context.sp() = framePointer + 2;
    static_assert(prologueStackPointerDelta() == sizeof(void*) * 2);''',
 '''#elif CPU(PPC64LE)
    // move(framePointerRegister, stackPointerRegister);
    // popFramePointerAndLinkRegister(): [cfr + 0] CallerFrame, [cfr + 8] ReturnPC.
    // The link register is an SPR on PowerPC, not a GPR, and the probe's
    // return path restores it from cpu.sprs[lr] (MacroAssemblerPPC64.cpp).
    context.fp() = std::bit_cast<UCPURegister*>(*framePointer);
    context.spr(PPC64Registers::lr) = std::bit_cast<UCPURegister>(*(framePointer + 1));
    context.sp() = framePointer + 2;
    static_assert(prologueStackPointerDelta() == sizeof(void*) * 2);'''),
# --- b3/B3LowerToAir.cpp --------------------------------------------------
('AFTER', J + 'b3/B3LowerToAir.cpp',
 """        case B3::CCall: {
            CCallValue* cCall = m_value->as<CCallValue>();
            bool deferToAfterRegAlloc = m_isRare && m_code.optLevel() >= 2 && !isARM_THUMB2();""",
 """
            // ppc64le: keep any CCall that touches a Float off the cold path.
            //
            // Both halves of the ELFv2 float seam are handled by the in-place
            // expansion below -- ConvertFloatToDouble into an argument FPR,
            // ConvertDoubleToFloat out of the result FPR -- because a float
            // lives in an FPR in DOUBLE format across a C call here while this
            // port's Float type is the raw single everywhere inside a
            // procedure. AirLowerAfterRegAlloc's ColdCCall arm builds its pre-
            // and post-call shuffles with widthForType(), so a Float moves as
            // Width32 (fmr, raw bits): the callee would read 1.0f as
            // ~1.06e-314, and a float result would come back as +0.0 because
            // word 1 of 0x3ff0000000000000 is zero. It runs after register
            // allocation and so cannot mint the Tmp a conversion needs, and
            // open-coding one against physical registers there would have to
            // reason about scratch availability and a stack-homed argument. So
            // route these through the expansion that is already correct and
            // already tested instead.
            //
            // The cost is that a rare float-taking or float-returning C call is
            // expanded in place rather than out of line. The calls this applies
            // to are B3LowerMacrosAfterOptimizations' float math helpers
            // (ceilFloat, floorFloat, truncFloat, and sqrtFloat/roundFloat/
            // stdPowFloat behind them), which are small and few.
            if (isPPC64() && deferToAfterRegAlloc) {
                bool touchesFloat = cCall->type() == Float;
                for (unsigned i = 1; !touchesFloat && i < cCall->numChildren(); ++i)
                    touchesFloat = cCall->child(i)->type() == Float;
                if (touchesFloat)
                    deferToAfterRegAlloc = false;
            }
"""),

# --- b3/air/AirGenerate.cpp -----------------------------------------------
('AFTER', J + 'b3/air/AirGenerate.cpp',
 '    DisallowMacroScratchRegisterUsage disallowScratch(jit);',
 """    // On this target the two MacroAssembler scratch registers are marked
    // isReserved in PPC64Registers.h, so Air never allocates them and there is
    // nothing of Air's to corrupt by using them here. That is not true on
    // ARM64 or x86-64, where ip0/ip1 and r11 are ordinary allocatable
    // registers -- which is what the Disallow above is for. See
    // powerpc64le-handbook docs/jsc-ppc64le-air-bringup.md section 5.
    AllowMacroScratchRegisterUsageIf allowScratchOnPPC64(jit, isPPC64());"""),

# --- b3/air/AirHandleCalleeSaves.cpp -------------------------------------
('AFTER', J + 'b3/air/AirHandleCalleeSaves.cpp',
 "    usedCalleeSaves.exclude(RegisterSet::stackRegisters()); // We don't need to save FP here.",
 """
    // The MacroAssembler's own scratch registers, which no Inst names.
    //
    // Neither caller of this function can see them: the graph-colouring path
    // scans the Insts, and the linear-scan path passes every callee save and
    // then filters by mutableRegs(), which is the allocation pool that r29 and
    // r30 are now reserved out of. They are merged AFTER those filters,
    // because the filters are about what the allocator touched and this is
    // about what the assembler touched.
    //
    // It matters here and almost nowhere else, because on ppc64le the two
    // scratch registers are r29 and r30 and ELFv2 makes them NON-VOLATILE.
    // This is also a pre-existing hole that reserving them turned from
    // intermittent into deterministic: before, a procedure the allocator
    // happened to give r29 got a save as a side effect, and one it did not,
    // did not.
    //
    // The alternative was measured rather than argued. Leaving them out --
    // relying on this port's standing contract that r29 and r30 are clobbered
    // by all JIT code and saved once at VM entry (jsc-ppc64le-port.md section
    // 5.2), which is how the LLInt, Baseline and DFG already work -- gives
    // testb3 796 of 998 groups with 25 SIGSEGVs. Saving them here gives 812
    // with 15. The contract holds for a JIT caller and not for testb3 and
    // testair, which enter Air code from C++ with live values in both.
    //
    // The 15 that remain are the CheckValue family, and they are the cost of
    // this choice rather than a defect in it: their generators end
    // `jit.emitFunctionEpilogue(); jit.ret();`, which restores fp and lr and
    // not the callee saves. Upstream can write that because on x86-64 and
    // ARM64 those small procedures have no callee-save area; giving every Air
    // procedure on this target one invalidates it. Air's own epilogue
    // (AirCode.cpp emitEpilogue) does emitRestore first and is correct.
    if (isPPC64()) {
        RegisterSet macroScratch = RegisterSet::macroClobberedGPRs();
        macroScratch.filter(RegisterSet::calleeSaveRegisters());
        usedCalleeSaves.merge(macroScratch);
    }
"""),

# --- dfg/DFGSpeculativeJIT.cpp -------------------------------------------
# The Int32 remainder path. Upstream restructured its fork to key on
# HAVE(ARM_IDIV_INSTRUCTIONS); the Int52 path below still reads
# `#elif CPU(ARM64)` and is covered by the patch series. Anchored on the line
# below it, because the fork line itself now occurs twice in this file.
('REPLACE', J + 'dfg/DFGSpeculativeJIT.cpp',
 """#elif HAVE(ARM_IDIV_INSTRUCTIONS) || CPU(ARM64)
        GPRTemporary quotientThenRemainder(this);""",
 """#elif HAVE(ARM_IDIV_INSTRUCTIONS) || CPU(ARM64) || CPU(PPC64LE)
        GPRTemporary quotientThenRemainder(this);"""),

# --- llint/InPlaceInterpreter64.asm --------------------------------------
('REPLACE', J + 'llint/InPlaceInterpreter64.asm',
 """    storep sc0, ReturnPC[sc2]
elsif ARM64 or ARM64E or ARMv7 or RISCV64""",
 """    storep sc0, ReturnPC[sc2]
elsif ARM64 or ARM64E or ARMv7 or RISCV64 or PPC64"""),

# --- llint/LowLevelInterpreter.cpp ---------------------------------------
('AFTER', J + 'llint/LowLevelInterpreter.cpp',
 '#define OFFLINE_ASM_ALIGN_TRAP(align) OFFLINE_ASM_BEGIN_SPACER "\\n .balignw " #align ", 0x9002\\n" // pad with c.ebreak instructions',
 '#elif CPU(PPC64LE)\n'
 '#define OFFLINE_ASM_ALIGN_TRAP(align) OFFLINE_ASM_BEGIN_SPACER "\\n .balignl " #align ", 0x7fe00008\\n" // pad with trap instructions'),

# --- offlineasm/instructions.rb ------------------------------------------
('REPLACE', J + 'offlineasm/instructions.rb',
 'INSTRUCTIONS = MACRO_INSTRUCTIONS + X86_INSTRUCTIONS + X86_SIMD_INSTRUCTIONS + ARM_INSTRUCTIONS + ARM64_INSTRUCTIONS + ARM64_SIMD_INSTRUCTIONS + RISC_INSTRUCTIONS + MIPS_INSTRUCTIONS + CXX_INSTRUCTIONS',
 'INSTRUCTIONS = MACRO_INSTRUCTIONS + X86_INSTRUCTIONS + X86_SIMD_INSTRUCTIONS + ARM_INSTRUCTIONS + ARM64_INSTRUCTIONS + ARM64_SIMD_INSTRUCTIONS + RISC_INSTRUCTIONS + PPC64_INSTRUCTIONS + MIPS_INSTRUCTIONS + CXX_INSTRUCTIONS'),

# --- runtime/JSCPtrTag.h -------------------------------------------------
('REPLACE', J + 'runtime/JSCPtrTag.h',
 '        static_assert(tag == OperationPtrTag);',
 '        static_assert(tag == OperationPtrTag || tag == LLIntEntryPtrTag);'),

# --- WTF/wtf/PlatformEnable.h -------------------------------------------
# Upstream has since split this into an outer ENABLE(JIT) test and an inner
# per-CPU one and added ARM_THUMB2, so only the inner condition is ours.
('REPLACE', W + 'PlatformEnable.h',
 '#if (CPU(ARM64) && CPU(ADDRESS64)) || CPU(ARM_THUMB2)',
 """/* Jump islands are needed by any target whose direct branch cannot reach
   across the whole executable pool. ARM64's `b` reaches +-128 MiB; PPC64's
   reaches +-32 MiB, and JSTests asks for pools far larger than that by name
   (--jitMemoryReservationSize=268435456), so ppc64le needs the same
   machinery. See jsc-ppc64le-port.md section 16. */
#if (CPU(ARM64) && CPU(ADDRESS64)) || CPU(ARM_THUMB2) || (CPU(PPC64LE) && CPU(ADDRESS64))"""),

# --- assembler/MacroAssembler.h ------------------------------------------
# Upstream added ARM_THUMB2 to two of these three lists; the port adds
# PPC64LE to each. The third is anchored on the declaration below it because
# the list itself is not unique in this file.
('REPLACE', J + 'assembler/MacroAssembler.h',
 '#if CPU(ARM64) || CPU(ARM_THUMB2) || CPU(X86_64) || CPU(RISCV64)',
 '#if CPU(ARM64) || CPU(ARM_THUMB2) || CPU(X86_64) || CPU(RISCV64) || CPU(PPC64LE)'),

('REPLACE', J + 'assembler/MacroAssembler.h',
 '#if CPU(ARM64) || CPU(X86_64) || CPU(RISCV64) || CPU(ARM_THUMB2)',
 '#if CPU(ARM64) || CPU(X86_64) || CPU(RISCV64) || CPU(ARM_THUMB2) || CPU(PPC64LE)'),

('REPLACE', J + 'assembler/MacroAssembler.h',
 """#if CPU(ARM64) || CPU(X86_64) || CPU(RISCV64)
    using MacroAssemblerBase::add64;""",
 """#if CPU(ARM64) || CPU(X86_64) || CPU(RISCV64) || CPU(PPC64LE)
    using MacroAssemblerBase::add64;"""),

# --- assembler/ProbeContext.h --------------------------------------------
('AFTER', J + 'assembler/ProbeContext.h',
 '    return *reinterpret_cast<void**>(&spr(RISCV64Registers::pc));',
 """#elif CPU(PPC64LE)
    return *reinterpret_cast<void**>(&spr(PPC64Registers::pc));"""),

('AFTER', J + 'assembler/ProbeContext.h',
 '    return *reinterpret_cast<void**>(&gpr(RISCV64Registers::fp));',
 """#elif CPU(PPC64LE)
    return *reinterpret_cast<void**>(&gpr(PPC64Registers::fp));"""),

('AFTER', J + 'assembler/ProbeContext.h',
 '    return *reinterpret_cast<void**>(&gpr(RISCV64Registers::sp));',
 """#elif CPU(PPC64LE)
    return *reinterpret_cast<void**>(&gpr(PPC64Registers::sp));"""),

# --- bytecode/InlineAccess.h ---------------------------------------------
('AFTER', J + 'bytecode/InlineAccess.h',
 """#elif CPU(RISCV64)
        return 44;""",
 """#elif CPU(PPC64LE)
        // Measured, not guessed: `testmasm dumpInlineAccessSizes` assembles
        // each inline-cache shape and prints its byte count. On this port
        //
        //     string length                 56
        //     out of line offset cache      40
        //     inline offset cache           36
        //     replace cache                 36
        //     replace out of line cache     40
        //     array length                  32
        //
        // and the three constants are the maxima of the groups the comments
        // above describe. The measurement is the worst case for each shape,
        // because dumpCacheSizesAndCrash uses a deliberately large structure
        // ID and property offset, and it is exactly the size of those
        // constants that makes a PowerPC sequence long.
        //
        // Re-measure whenever the IC sequences change. Getting these too small
        // does not corrupt anything -- linkCodeInline just declines to inline
        // and the IC goes out of line, silently -- which is why the suite
        // cannot be the control for them and the dump has to be.
        return 40; // max(inline offset 36, out of line offset 40)"""),

('AFTER', J + 'bytecode/InlineAccess.h',
 """#elif CPU(RISCV64)
        return 52;""",
 """#elif CPU(PPC64LE)
        return 40; // max(replace 36, replace out of line 40)"""),

('AFTER', J + 'bytecode/InlineAccess.h',
 """#elif CPU(RISCV64)
        size_t size = 60;""",
 """#elif CPU(PPC64LE)
        size_t size = 56; // string length 56, array length 32"""),

# --- jit/AssemblyHelpers.h -----------------------------------------------
('REPLACE', J + 'jit/AssemblyHelpers.h',
 """#if CPU(ARM64) || CPU(RISCV64)
        pushPair(GPRInfo::numberTagRegister, GPRInfo::notCellMaskRegister);""",
 """#if CPU(ARM64) || CPU(RISCV64) || CPU(PPC64LE)
        pushPair(GPRInfo::numberTagRegister, GPRInfo::notCellMaskRegister);"""),

('REPLACE', J + 'jit/AssemblyHelpers.h',
 """#if CPU(ARM64) || CPU(RISCV64)
        popPair(GPRInfo::numberTagRegister, GPRInfo::notCellMaskRegister);""",
 """#if CPU(ARM64) || CPU(RISCV64) || CPU(PPC64LE)
        popPair(GPRInfo::numberTagRegister, GPRInfo::notCellMaskRegister);"""),

('REPLACE', J + 'jit/AssemblyHelpers.h',
 """#if CPU(ARM64) || CPU(X86_64) || CPU(RISCV64) || CPU(ARM_THUMB2)
    JumpList checkWasmStackOverflow(GPRReg instanceGPR, TrustedImm32, GPRReg framePointerGPR);""",
 """#if CPU(ARM64) || CPU(X86_64) || CPU(RISCV64) || CPU(ARM_THUMB2) || CPU(PPC64LE)
    JumpList checkWasmStackOverflow(GPRReg instanceGPR, TrustedImm32, GPRReg framePointerGPR);"""),

# --- jit/CCallHelpers.cpp ------------------------------------------------
('AFTER', J + 'jit/CCallHelpers.cpp',
 """#elif CPU(ARM64) || CPU(ARM_THUMB2) || CPU(RISCV64)
    pushPair(framePointerRegister, linkRegister);""",
 """#elif CPU(PPC64LE)
    // No linkRegister GPR on PowerPC: the return address lives in an SPR and
    // is shuttled through r0. Same 16-byte frame, same slot order.
    pushFramePointerAndLinkRegister();"""),

('AFTER', J + 'jit/CCallHelpers.cpp',
 """#elif CPU(ARM64) || CPU(ARM_THUMB2) || CPU(RISCV64)
    popPair(framePointerRegister, linkRegister);""",
 """#elif CPU(PPC64LE)
    popFramePointerAndLinkRegister();"""),

# --- jit/GdbJIT.cpp ------------------------------------------------------
# Both lists are spelled the same, so each is anchored on what follows it.
('REPLACE', J + 'jit/GdbJIT.cpp',
 """#elif CPU(X86_64) || CPU(ARM64) || CPU(RISCV64)
        const uint8_t ident[16] = {""",
 """#elif CPU(X86_64) || CPU(ARM64) || CPU(RISCV64) || CPU(PPC64LE)
        const uint8_t ident[16] = {"""),

('REPLACE', J + 'jit/GdbJIT.cpp',
 """#elif CPU(X86_64) || CPU(ARM64) || CPU(RISCV64)
    struct SerializedLayout {""",
 """#elif CPU(X86_64) || CPU(ARM64) || CPU(RISCV64) || CPU(PPC64LE)
    struct SerializedLayout {"""),

# --- CMakeLists.txt ------------------------------------------------------
('REPLACE', J + 'CMakeLists.txt',
 '''elseif (WTF_CPU_RISCV64)
    set(OFFLINE_ASM_BACKEND "RISCV64")''',
 '''elseif (WTF_CPU_RISCV64)
    set(OFFLINE_ASM_BACKEND "RISCV64")
elseif (WTF_CPU_PPC64LE)
    set(OFFLINE_ASM_BACKEND "PPC64")'''),

# MacroAssembler.h is in this list and so are its per-architecture headers,
# so ours has to be here too or the staged copy will not compile.
('BEFORE', J + 'CMakeLists.txt',
 '    assembler/MacroAssemblerX86_64.h',
 '    assembler/MacroAssemblerPPC64.h'),

('BEFORE', J + 'CMakeLists.txt',
 '    assembler/Printer.h',
 '''    assembler/PPC64Assembler.h
    assembler/PPC64Registers.h'''),

('AFTER', J + 'CMakeLists.txt',
 '    wasm/WasmAddressType.h',
 '    wasm/WasmAirArgShim.h'),

# --- jit/RegisterSet.cpp -------------------------------------------------
('REPLACE', J + 'jit/RegisterSet.cpp',
 '''#elif CPU(ARM64) || CPU(RISCV64)
    result.add(MacroAssembler::dataTempRegister);''',
 '''#elif CPU(ARM64) || CPU(RISCV64) || CPU(PPC64LE)
    result.add(MacroAssembler::dataTempRegister);'''),

('REPLACE', J + 'jit/RegisterSet.cpp',
 '''#elif CPU(RISCV64)
    result.add(MacroAssembler::fpTempRegister, IgnoreVectors);
    result.add(MacroAssembler::fpTempRegister2, IgnoreVectors);''',
 '''#elif CPU(RISCV64) || CPU(PPC64LE)
    result.add(MacroAssembler::fpTempRegister, IgnoreVectors);
    result.add(MacroAssembler::fpTempRegister2, IgnoreVectors);'''),

('REPLACE', J + 'jit/RegisterSet.cpp',
 '''#elif CPU(ARM64) || CPU(RISCV64)
    result.add(GPRInfo::regCS6);''',
 '''#elif CPU(ARM64) || CPU(RISCV64) || CPU(PPC64LE)
    result.add(GPRInfo::regCS6);'''),

('REPLACE', J + 'jit/RegisterSet.cpp',
 '''#elif CPU(ARM64) || CPU(RISCV64)
    static_assert(GPRInfo::regCS7 == GPRInfo::jitDataRegister);''',
 '''#elif CPU(ARM64) || CPU(RISCV64) || CPU(PPC64LE)
    static_assert(GPRInfo::regCS7 == GPRInfo::jitDataRegister);'''),

('REPLACE', J + 'jit/RegisterSet.cpp',
 '''#elif CPU(ARM64) || CPU(RISCV64)
    registers.add(GPRInfo::regCS6); // MC''',
 '''#elif CPU(ARM64) || CPU(RISCV64) || CPU(PPC64LE)
    registers.add(GPRInfo::regCS6); // MC'''),

# --- llint/LLIntOfflineAsmConfig.h --------------------------------------
('AFTER', J + 'llint/LLIntOfflineAsmConfig.h',
 '''#define OFFLINE_ASM_ARMv7s 0
#define OFFLINE_ASM_RISCV64 0''',
 '#define OFFLINE_ASM_PPC64 0'),

('AFTER', J + 'llint/LLIntOfflineAsmConfig.h',
 '''#else
#define OFFLINE_ASM_RISCV64 0
#endif''',
 '''
#if CPU(PPC64LE)
#define OFFLINE_ASM_PPC64 1
#else
#define OFFLINE_ASM_PPC64 0
#endif'''),

# --- jit/GPRInfo.h ------------------------------------------------------
('AFTER', J + 'jit/GPRInfo.h',
 '#endif // CPU(RISCV64)',
 """
#if CPU(PPC64LE)

// ELFv2: r3-r10 are the argument/return registers, r11 and r12 the remaining
// volatiles (r12 is also the indirect-call target), r14-r31 nonvolatile.
// That is only ten volatile GPRs, three fewer than RISC-V or ARM64 give
// offlineasm, so t10-t12 come out of the callee-saved file (r25-r27) and the
// VM entry frame pays for them. This mirrors offlineasm/ppc64.rb exactly;
// see jsc-ppc64le-port.md section 5.2.
#define NUMBER_OF_ARGUMENT_REGISTERS 8u
// This sizes VMEntryRecord::calleeSaveRegistersBuffer, and it MUST equal the
// number of slots copyCalleeSavesToBuffer() writes in
// llint/LowLevelInterpreter.asm: regCS0-regCS10 (11) plus fpRegCS0-fpRegCS11
// (12). Getting it wrong is a silent buffer overflow past the end of the
// VMEntryRecord -- it cost a debugging session here, where 20 let the
// callee-save copy on the throw path run three slots past the record and
// overwrite the entry frame's saved r28/r29/r30.
#define NUMBER_OF_CALLEE_SAVES_REGISTERS 23u

class GPRInfo {
public:
    typedef GPRReg RegisterType;
    static constexpr unsigned numberOfRegisters = 13;
    static constexpr unsigned numberOfArgumentRegisters = NUMBER_OF_ARGUMENT_REGISTERS;

    static constexpr GPRReg callFrameRegister = PPC64Registers::r31;
    static constexpr GPRReg numberTagRegister = PPC64Registers::r22;   // csr8
    static constexpr GPRReg notCellMaskRegister = PPC64Registers::r23; // csr9
    static constexpr GPRReg jitDataRegister = PPC64Registers::r21;     // csr7 = PB
    static constexpr GPRReg wasmIPIntPCRegister = PPC64Registers::r21; // IPInt PC = csr7
    static constexpr GPRReg metadataTableRegister = PPC64Registers::r20; // csr6

    static constexpr GPRReg regT0 = PPC64Registers::r3;
    static constexpr GPRReg regT1 = PPC64Registers::r4;
    static constexpr GPRReg regT2 = PPC64Registers::r5;
    static constexpr GPRReg regT3 = PPC64Registers::r6;
    static constexpr GPRReg regT4 = PPC64Registers::r7;
    static constexpr GPRReg regT5 = PPC64Registers::r8;
    static constexpr GPRReg regT6 = PPC64Registers::r9;
    static constexpr GPRReg regT7 = PPC64Registers::r10;
    static constexpr GPRReg regT8 = PPC64Registers::r11;
    static constexpr GPRReg regT9 = PPC64Registers::r12;
    static constexpr GPRReg regT10 = PPC64Registers::r25;
    static constexpr GPRReg regT11 = PPC64Registers::r26;
    static constexpr GPRReg regT12 = PPC64Registers::r27;

    static constexpr GPRReg regCS0 = PPC64Registers::r14;
    static constexpr GPRReg regCS1 = PPC64Registers::r15;
    static constexpr GPRReg regCS2 = PPC64Registers::r16;
    static constexpr GPRReg regCS3 = PPC64Registers::r17;
    static constexpr GPRReg regCS4 = PPC64Registers::r18;
    static constexpr GPRReg regCS5 = PPC64Registers::r19;
    static constexpr GPRReg regCS6 = PPC64Registers::r20; // metadataTable in LLInt/Baseline / IPIntMC
    static constexpr GPRReg regCS7 = PPC64Registers::r21; // jitData / PB / IPIntPC
    static constexpr GPRReg regCS8 = PPC64Registers::r22; // numberTag
    static constexpr GPRReg regCS9 = PPC64Registers::r23; // notCellMask
    static constexpr GPRReg regCS10 = PPC64Registers::r24;

    static constexpr GPRReg argumentGPR0 = PPC64Registers::r3;  // regT0
    static constexpr GPRReg argumentGPR1 = PPC64Registers::r4;  // regT1
    static constexpr GPRReg argumentGPR2 = PPC64Registers::r5;  // regT2
    static constexpr GPRReg argumentGPR3 = PPC64Registers::r6;  // regT3
    static constexpr GPRReg argumentGPR4 = PPC64Registers::r7;  // regT4
    static constexpr GPRReg argumentGPR5 = PPC64Registers::r8;  // regT5
    static constexpr GPRReg argumentGPR6 = PPC64Registers::r9;  // regT6
    static constexpr GPRReg argumentGPR7 = PPC64Registers::r10; // regT7

    // r11 and r12 are the only volatile non-argument GPRs the ABI leaves.
    // r12 doubling as the ELFv2 indirect-call target means an indirect call
    // clobbers regT9; that is legal because every volatile register dies at
    // a call, but it is a constraint stage c has to respect.
    static constexpr GPRReg nonArgGPR0 = PPC64Registers::r11; // regT8
    static constexpr GPRReg nonArgGPR1 = PPC64Registers::r12; // regT9

    static constexpr GPRReg returnValueGPR = PPC64Registers::r3;  // regT0
    static constexpr GPRReg returnValueGPR2 = PPC64Registers::r4; // regT1

    static constexpr GPRReg nonPreservedNonReturnGPR = PPC64Registers::r5;      // regT2
    static constexpr GPRReg nonPreservedNonArgumentGPR0 = PPC64Registers::r11;  // regT8
    static constexpr GPRReg nonPreservedNonArgumentGPR1 = PPC64Registers::r12;  // regT9

    static constexpr GPRReg handlerGPR = GPRInfo::nonPreservedNonArgumentGPR1;

    static constexpr GPRReg wasmScratchGPR0 = PPC64Registers::r12; // regT9
    static constexpr GPRReg wasmScratchGPR1 = PPC64Registers::r25; // regT10
    static constexpr GPRReg wasmContextInstancePointer = regCS0;
    static constexpr GPRReg wasmBaseMemoryPointer = regCS3;
    static constexpr GPRReg wasmBoundsCheckingSizeRegister = regCS4;

    static constexpr GPRReg regWS0 = PPC64Registers::r12;
    static constexpr GPRReg regWS1 = PPC64Registers::r25;
    static constexpr GPRReg regWA0 = PPC64Registers::r3;
    static constexpr GPRReg regWA1 = PPC64Registers::r4;
    static constexpr GPRReg regWA2 = PPC64Registers::r5;
    static constexpr GPRReg regWA3 = PPC64Registers::r6;
    static constexpr GPRReg regWA4 = PPC64Registers::r7;
    static constexpr GPRReg regWA5 = PPC64Registers::r8;
    static constexpr GPRReg regWA6 = PPC64Registers::r9;
    static constexpr GPRReg regWA7 = PPC64Registers::r10;

    static constexpr GPRReg patchpointScratchRegister = PPC64Registers::r29; // dataTempRegister

    static constexpr GPRReg toRegister(unsigned index)
    {
        ASSERT_UNDER_CONSTEXPR_CONTEXT(index < numberOfRegisters);
        constexpr GPRReg registerForIndex[numberOfRegisters] = {
            regT0, regT1, regT2, regT3, regT4, regT5, regT6, regT7,
            regT8, regT9, regT10, regT11, regT12,
        };
        return registerForIndex[index];
    }

    static constexpr GPRReg toArgumentRegister(unsigned index)
    {
        ASSERT_UNDER_CONSTEXPR_CONTEXT(index < numberOfArgumentRegisters);
        constexpr GPRReg registerForIndex[numberOfArgumentRegisters] = {
            argumentGPR0, argumentGPR1, argumentGPR2, argumentGPR3,
            argumentGPR4, argumentGPR5, argumentGPR6, argumentGPR7,
        };
        return registerForIndex[index];
    }

    static unsigned toIndex(GPRReg reg)
    {
        ASSERT(reg != InvalidGPRReg);
        ASSERT(static_cast<int>(reg) < 32);
        // r0 r1 r2 are reserved; r3-r12 are regT0-regT9; r13-r24 are the
        // thread pointer and the callee-saves; r25-r27 are regT10-regT12;
        // r28-r31 are the offlineasm/MacroAssembler scratch and cfr.
        static const unsigned indexForRegister[32] = {
            InvalidIndex, InvalidIndex, InvalidIndex, 0, 1, 2, 3, 4,
            5, 6, 7, 8, 9, InvalidIndex, InvalidIndex, InvalidIndex,
            InvalidIndex, InvalidIndex, InvalidIndex, InvalidIndex, InvalidIndex, InvalidIndex, InvalidIndex, InvalidIndex,
            InvalidIndex, 10, 11, 12, InvalidIndex, InvalidIndex, InvalidIndex, InvalidIndex,
        };
        return indexForRegister[reg];
    }

    static unsigned toArgumentIndex(GPRReg reg)
    {
        ASSERT(reg != InvalidGPRReg);
        ASSERT(static_cast<int>(reg) < 32);
        if (reg < argumentGPR0 || reg > argumentGPR7)
            return InvalidIndex;
        return static_cast<unsigned>(reg) - 3;
    }

    static ASCIILiteral debugName(GPRReg reg)
    {
        ASSERT(reg != InvalidGPRReg);
        return MacroAssembler::gprName(reg);
    }

    static constexpr unsigned InvalidIndex = 0xffffffff;
};

#endif // CPU(PPC64LE)"""),

# --- llint/LowLevelInterpreter.asm ---------------------------------------
# Upstream has added ARMv7 to several of these lists since the port was
# written; each entry adds PPC64 to whatever is there now.
('REPLACE', J + 'llint/LowLevelInterpreter.asm',
 """    if ARM64 or ARM64E or RISCV64
        const metadataTable = csr6""",
 """    if ARM64 or ARM64E or RISCV64 or PPC64
        const metadataTable = csr6"""),

('REPLACE', J + 'llint/LowLevelInterpreter.asm',
 """if C_LOOP or ARM64 or ARM64E or X86_64 or RISCV64
    const CalleeSaveRegisterCount = 0""",
 """if C_LOOP or ARM64 or ARM64E or X86_64 or RISCV64
    const CalleeSaveRegisterCount = 0
elsif PPC64
    # ELFv2 leaves only r0 and r3-r12 volatile, which is three registers
    # short of what offlineasm wants: t0-t9 take r3-r12, so t10-t12 come from
    # r25-r27 and the temporary pool from r28-r30 -- six NONVOLATILE
    # registers that offlineasm treats as scratch. Every entry point C++ can
    # call therefore has to hand them back. This reserves the room for them
    # at the top of the VM entry frame (just below cfr); see
    # preserveNonvolatileTemporaries / restoreNonvolatileTemporaries below.
    const CalleeSaveRegisterCount = 6"""),

('REPLACE', J + 'llint/LowLevelInterpreter.asm',
 """macro copyCalleeSavesToEntryFrameCalleeSavesBuffer(entryFrame)
    if ARM64 or ARM64E or X86_64 or ARMv7 or RISCV64""",
 """macro copyCalleeSavesToEntryFrameCalleeSavesBuffer(entryFrame)
    if ARM64 or ARM64E or X86_64 or ARMv7 or RISCV64 or PPC64"""),

('REPLACE', J + 'llint/LowLevelInterpreter.asm',
 """macro copyCalleeSavesToVMEntryFrameCalleeSavesBuffer(vm, temp)
    if ARM64 or ARM64E or X86_64 or ARMv7 or RISCV64""",
 """macro copyCalleeSavesToVMEntryFrameCalleeSavesBuffer(vm, temp)
    if ARM64 or ARM64E or X86_64 or ARMv7 or RISCV64 or PPC64"""),

('REPLACE', J + 'llint/LowLevelInterpreter.asm',
 """macro restoreCalleeSavesFromVMEntryFrameCalleeSavesBuffer(vm, temp)
    if ARM64 or ARM64E or X86_64 or ARMv7 or RISCV64""",
 """macro restoreCalleeSavesFromVMEntryFrameCalleeSavesBuffer(vm, temp)
    if ARM64 or ARM64E or X86_64 or ARMv7 or RISCV64 or PPC64"""),

('REPLACE', J + 'llint/LowLevelInterpreter.asm',
 """macro preserveReturnAddressAfterCall(destinationRegister)
    if C_LOOP or ARMv7 or ARM64 or ARM64E or RISCV64""",
 """macro preserveReturnAddressAfterCall(destinationRegister)
    if C_LOOP or ARMv7 or ARM64 or ARM64E or RISCV64 or PPC64"""),

('REPLACE', J + 'llint/LowLevelInterpreter.asm',
 """    if ARMv7 or ARM64 or ARM64E or C_LOOP or RISCV64
        subi CallerFrameAndPCSize, temp2""",
 """    if ARMv7 or ARM64 or ARM64E or C_LOOP or RISCV64 or PPC64
        subi CallerFrameAndPCSize, temp2"""),

('AFTER', J + 'llint/LowLevelInterpreter.asm',
 """        move callee, t5
        size(callNarrow, callWide16, callWide32, macro (gen) gen() end)""",
 """    elsif PPC64
        # The callee is generated code and sp is already the callee's frame:
        # the generic `call` would reserve an ELFv2 linkage area over it. See
        # PPC64_INSTRUCTIONS in offlineasm/instructions.rb.
        move callee, t5
        ppc64JSCall(t5)"""),

# The LLInt entry thunks get their OWN frame rather than the cfr headroom,
# because this function has no VMEntryRecord and crash() below is a call.
# That is also why upstream's pushCalleeSaves()/popCalleeSaves() hook is not
# used for this target even though it exists and is called right here: it is
# called at sites that have no reserved save area at all.
('AFTER', J + 'llint/LowLevelInterpreter.asm',
 """macro entry(kind, initialize)
    global _%kind%_entry
    _%kind%_entry:
        functionPrologue()
        pushCalleeSaves()""",
 """
        if PPC64
            # Called directly from C++ (JSC::LLInt::initialize). The body
            # materialises 500-odd opcode addresses through the temporary
            # pool, so r28-r30 are certainly clobbered. Give them back.
            emit "addi 1, 1, -80"
            emit "std 25, 32(1)"
            emit "std 26, 40(1)"
            emit "std 27, 48(1)"
            emit "std 28, 56(1)"
            emit "std 29, 64(1)"
            emit "std 30, 72(1)"
        end"""),

('BEFORE', J + 'llint/LowLevelInterpreter.asm',
 """        popCalleeSaves()
        functionEpilogue()
        ret
end

# Entry point for the llint to initialize.""",
 """        if PPC64
            emit "ld 25, 32(1)"
            emit "ld 26, 40(1)"
            emit "ld 27, 48(1)"
            emit "ld 28, 56(1)"
            emit "ld 29, 64(1)"
            emit "ld 30, 72(1)"
            emit "addi 1, 1, 80"
        end
"""),

# --- llint/LowLevelInterpreter64.asm ------------------------------------
('AFTER', J + 'llint/LowLevelInterpreter64.asm',
 """macro doVMEntry(makeCall)
    functionPrologue()
    pushCalleeSaves()""",
 '    preserveNonvolatileTemporaries()'),

# Three sites, byte-identical except that the first has a blank line before
# popCalleeSaves() and the other two do not -- hence two entries with declared
# counts rather than one. On every other target the macro's else arm is the
# `subp` it replaces, so this is a no-op for them.
('REPLACE', J + 'llint/LowLevelInterpreter64.asm',
 """    subp cfr, CalleeRegisterSaveSize, sp

    popCalleeSaves()""",
 """    restoreNonvolatileTemporariesAndResetSP()

    popCalleeSaves()"""),

('REPLACE*2', J + 'llint/LowLevelInterpreter64.asm',
 """    subp cfr, CalleeRegisterSaveSize, sp
    popCalleeSaves()""",
 """    restoreNonvolatileTemporariesAndResetSP()
    popCalleeSaves()"""),

# --- b3/air/AirArg.h -----------------------------------------------------
('REPLACE', J + 'b3/air/AirArg.h',
 """        case 1:
            if (isX86() || isARM64() || isARM_THUMB2())""",
 """        case 1:
            // POWER's indexed addressing is the X-form, base + index, with no
            // shift and no displacement: ldx RT,RA,RB is RA + RB and nothing
            // else. Scale 1 is therefore the only scale that exists here, and
            // it exists for every width. Measured with the assembler as the
            // encodability oracle: `ldx 3,4,8(5)` is rejected outright.
            if (isX86() || isARM64() || isARM_THUMB2() || isPPC64())"""),

('BEFORE', J + 'b3/air/AirArg.h',
 """        if (isARM64())
            return ARM64LogicalImmediate::create32(value).isValid();""",
 """        if (isPPC64()) {
            // MacroAssemblerPPC64's xor32(TrustedImm32, src, dest) casts to
            // uint32_t and lands in xorImmediate64's 32-bit arm, which is
            // xoris/xori/move and takes NO scratch register -- xorImmediate64
            // only reaches constantScratch() for a value with bits above 32,
            // which this form cannot present. That matters because Air
            // generates under DisallowMacroScratchRegisterUsage.
            //
            // Only Xor32 declares a BitImm form for this target. And32 and
            // Or32 keep theirs arm64-only until their immediate paths are
            // audited the same way, so widening this predicate cannot reach
            // them.
            return WTF::isRepresentableAs<int32_t>(value);
        }"""),

# Upstream now threads the opcode into isValidIndexForm itself -- as the FIRST
# parameter, and for the same reason the port needed it (ARM_THUMB2 cannot do
# an indexed MoveFloat/MoveDouble). So the port's signature change, its call
# site in isValidForm and its opcode_generator.rb change are all gone, and
# only this arm is left. See OBSOLETE for the generator.
('BEFORE', J + 'b3/air/AirArg.h',
 """        if (isARM_THUMB2()) {
            switch (opcode) {
            case MoveFloat:""",
 """        if (isPPC64()) {
            // Lea is the one opcode here that does not touch memory: it is an
            // address COMPUTATION, so leaIndex64 adds base and index into the
            // destination and then adds the displacement with an addi. A
            // displacement therefore costs one instruction rather than being
            // unencodable, and saying so is what lets tryAppendLea fold
            // Add(Add(@x, @y), $c) on this target.
            //
            // Every other opcode reaching here IS a memory access, and the
            // X-form has no displacement field at all for any width -- so the
            // answer is ARM64's, for the opposite reason: ARM64 has a
            // displacement and cannot scale it here, POWER has none to scale.
            if (opcode == Air::Lea32 || opcode == Air::Lea64)
                return true;
            return !offset;
        }"""),

# --- jit/CCallHelpers.h --------------------------------------------------
('BEFORE', J + 'jit/CCallHelpers.h',
 '#include <wtf/TZoneMalloc.h>',
 '#include "NativeArgumentCursor.h"'),

# ELFv2 chooses an argument's register by its ORDINAL, not by how many
# same-class arguments came before it: an integer following a double goes in
# r5, because the double consumed the doubleword that r4/f1 share. The cursor
# owns that rule. Upstream has since added extraGPRArgs to the collection and
# folds it into argCount(GPRReg) -- `numGPRArgs + extraGPRArgs` -- so the
# cursor is fed the same sum, which keeps this a pure refactor on every other
# target. (extraGPRArgs is only ever nonzero under CPU(ARM_THUMB2).)
('REPLACE', J + 'jit/CCallHelpers.h',
 """        using InfoType = InfoTypeForReg<RegType>;
        unsigned numArgRegisters = InfoType::numberOfArgumentRegisters;
        unsigned currentArgCount = argSourceRegs.argCount(arg);
        if (currentArgCount < numArgRegisters) {
            auto updatedArgSourceRegs = argSourceRegs.pushRegArg(arg, InfoType::toArgumentRegister(currentArgCount));
            setupArgumentsImpl<OperationType>(updatedArgSourceRegs, args...);
            return;
        }""",
 """        constexpr bool argumentIsFloatClass = std::is_same_v<RegType, FPRReg>;
        constexpr NativeArgumentCursor cursor {
            .ordinal = numGPRArgs + extraGPRArgs + numFPRArgs,
            .gprsUsed = numGPRArgs + extraGPRArgs,
            .fprsUsed = numFPRArgs,
        };
        constexpr auto placed = cursor.place(argumentIsFloatClass ? NativeArgumentClass::Double : NativeArgumentClass::Integer);
        constexpr NativeArgumentHome home = placed.first;

        if constexpr (argumentIsFloatClass) {
            // A float-class argument never homes to a GPR on any convention
            // this marshaller serves; on ELFv2 that is a theorem for scalar
            // argument lists rather than a convention (handbook 2.3).
            static_assert(home.kind != NativeArgumentHome::Kind::FPRAndGPR, "JIT operations are prototyped by construction; a variadic home should be unreachable");
            static_assert(home.kind != NativeArgumentHome::Kind::GPR, "A float-class argument must never be marshalled into a GPR");
            if constexpr (home.kind == NativeArgumentHome::Kind::FPR) {
                auto updatedArgSourceRegs = argSourceRegs.pushRegArg(arg, nativeFloatArgumentRegister(home.index));
                setupArgumentsImpl<OperationType>(updatedArgSourceRegs, args...);
                return;
            }
        } else {
            if constexpr (home.kind == NativeArgumentHome::Kind::GPR) {
                auto updatedArgSourceRegs = argSourceRegs.pushRegArg(arg, nativeIntegerArgumentRegister(home.index));
                setupArgumentsImpl<OperationType>(updatedArgSourceRegs, args...);
                return;
            }
        }"""),

# The TrustedImm destination, chosen by the same ordinal.
('REPLACE', J + 'jit/CCallHelpers.h',
 """        auto numArgRegisters = GPRInfo::numberOfArgumentRegisters;
        auto currentArgCount = numGPRArgs + extraGPRArgs;
        if (currentArgCount < numArgRegisters) {
            setupArgumentsImpl<OperationType>(argSourceRegs.addGPRArg(), args...);
            move(arg, GPRInfo::toArgumentRegister(currentArgCount));
            return;
        }""",
 """        constexpr NativeArgumentCursor cursor {
            .ordinal = numGPRArgs + extraGPRArgs + numFPRArgs,
            .gprsUsed = numGPRArgs + extraGPRArgs,
            .fprsUsed = numFPRArgs,
        };
        constexpr NativeArgumentHome home = cursor.place(NativeArgumentClass::Integer).first;
        if constexpr (home.kind == NativeArgumentHome::Kind::GPR) {
            setupArgumentsImpl<OperationType>(argSourceRegs.addGPRArg(), args...);
            move(arg, nativeIntegerArgumentRegister(home.index));
            return;
        }"""),

# And the ConstantMaterializer destination.
('REPLACE', J + 'jit/CCallHelpers.h',
 """        auto numArgRegisters = GPRInfo::numberOfArgumentRegisters;
        auto currentArgCount = numGPRArgs + extraGPRArgs;
        if (currentArgCount < numArgRegisters) {
            setupArgumentsImpl<OperationType>(argSourceRegs.addGPRArg(), args...);
            arg.materialize(*this, GPRInfo::toArgumentRegister(currentArgCount));
            return;
        }""",
 """        constexpr NativeArgumentCursor cursor {
            .ordinal = numGPRArgs + extraGPRArgs + numFPRArgs,
            .gprsUsed = numGPRArgs + extraGPRArgs,
            .fprsUsed = numFPRArgs,
        };
        constexpr NativeArgumentHome home = cursor.place(NativeArgumentClass::Integer).first;
        if constexpr (home.kind == NativeArgumentHome::Kind::GPR) {
            setupArgumentsImpl<OperationType>(argSourceRegs.addGPRArg(), args...);
            arg.materialize(*this, nativeIntegerArgumentRegister(home.index));
            return;
        }"""),

('REPLACE', J + 'jit/CCallHelpers.h',
 """#if CPU(ARM_THUMB2) || CPU(ARM64) || CPU(RISCV64)
        loadPtr(Address(framePointerRegister, CallFrame::returnPCOffset()), linkRegister);""",
 """#if CPU(PPC64LE)
        // Same shape as the ARM64/RISCV64 arm: the return address goes back
        // into the link register because that is where a PowerPC callee's
        // prologue will look for it. It is an SPR here, so it is loaded via
        // loadToLinkRegister rather than into a named GPR.
        loadToLinkRegister(Address(framePointerRegister, CallFrame::returnPCOffset()));
        subPtr(TrustedImm32(2 * sizeof(void*)), newFrameSizeGPR);
#elif CPU(ARM_THUMB2) || CPU(ARM64) || CPU(RISCV64)
        loadPtr(Address(framePointerRegister, CallFrame::returnPCOffset()), linkRegister);"""),

# --- b3/air/AirCode.cpp --------------------------------------------------
('REPLACE', J + 'b3/air/AirCode.cpp',
 '    AllowMacroScratchRegisterUsageIf allowScratch(jit, isARM64() || isARM_THUMB2());',
 '    AllowMacroScratchRegisterUsageIf allowScratch(jit, isARM64() || isARM_THUMB2() || isPPC64());'),

('AFTER', J + 'b3/air/AirCode.cpp',
 """            auto calleeSave = RegisterSet::calleeSaveRegisters();""",
 """            if constexpr (isPPC64()) {
                // Air may only allocate a callee-save that the VM entry frame
                // can RECORD. When an exception unwinds,
                // copyCalleeSavesToEntryFrameCalleeSavesBuffer walks the
                // procedure's callee-save list and looks every register up in
                // vmCalleeSaveBufferSlotsByRegIndex; a register with no slot
                // either aborts on RELEASE_ASSERT(bufferSlot >= 0) or, if that
                // is loosened, has its live value silently dropped.
                //
                // On this target the two sets are not the same. ELFv2 makes
                // r14-r28 nonvolatile, but the buffer covers r14-r24 plus
                // f14-f25, which is what NUMBER_OF_CALLEE_SAVES_REGISTERS (23)
                // and copyCalleeSavesToBuffer in LowLevelInterpreter.asm are
                // sized and written for. Extending the buffer instead would
                // mean csr names for r25-r28, which are already regT10-regT12
                // in GPRInfo -- dual-naming registers to paper over this.
                //
                // Measured: with r25-r28 allocatable and dropped on unwind,
                // stress/generator-fib-ftl-and-string.js and
                // stress/arrowfunction-run-10000-1.js die in
                // operationValueAddProfiledNoOptimize on a JSValue that fails
                // downcast<JSObject>. Keeping them out of the pool costs four
                // GPRs and leaves 21, against x86_64's 14.
                //
                // r29/r30 are reserved and already excluded above, but
                // AirHandleCalleeSaves merges them into every procedure's list
                // regardless; they are safe to drop on unwind precisely because
                // being reserved means nothing holds a live value in them. See
                // RegisterSet::vmEntryPreservedTemporaries().
                all.exclude(RegisterSet::unrecordableCalleeSaveRegisters());
            }"""),

# --- b3/air/AirLowerStackArgs.cpp ---------------------------------------
('BEFORE', J + 'b3/air/AirLowerStackArgs.cpp',
 """#elif CPU(X86_64)
                UNUSED_PARAM(insertionIndex);""",
 """#elif CPU(PPC64LE)
                // Same materialisation, one instruction shorter, and without
                // ever making the materialised register a base. POWER's X-form
                // is base+index with no displacement, so the offset can live in
                // extendedOffsetAddrRegister() -- r0 -- while sp stays the base.
                // That is what lets r0 serve at all: it is the literal zero in
                // an RA field and an ordinary register in an RB field.
                //
                // The Add64 the ARM64 arm inserts is also unavailable here. Air
                // declares Add64 only under the 64: tag, which means x86-64 or
                // arm64, so this target has no Add64 form to insert. Folding the
                // addition into the addressing mode removes the need for one.
                RELEASE_ASSERT(!extendedOffsetAddrRegInUse);
                Air::Tmp tmp = Air::Tmp(extendedOffsetAddrRegister());
                extendedOffsetAddrRegInUse = true;

                Arg largeOffset = Arg::isValidImmForm(offsetFromSP) ? Arg::imm(offsetFromSP) : Arg::bigImm(offsetFromSP);
                insertionSet.insert(insertionIndex, Move, inst.origin, largeOffset, tmp);
                result = Arg::index(Air::Tmp(MacroAssembler::stackPointerRegister), tmp, 1, 0);
                RELEASE_ASSERT(result.isValidForm(Move, width));
                return result;"""),

('REPLACE', J + 'b3/air/AirLowerStackArgs.cpp',
 '#elif CPU(X86_64) || CPU(ARM)',
 """#elif CPU(X86_64) || CPU(ARM) || CPU(PPC64LE)
                            // POWER's r0-reads-as-zero is positional -- it is
                            // the literal zero only in the RA field of a
                            // load/store or addi, and the contents of r0 in a
                            // source field -- so there is no register that
                            // reads zero everywhere and Arg::ZeroReg has no
                            // encoding here. The x86 shape is the correct one,
                            // and the Move32 Imm/Addr and Imm/Index forms are
                            // tagged ppc64 in AirOpcode.opcodes to supply it."""),

# --- b3/B3CheckSpecial.cpp ----------------------------------------------
('REPLACE', J + 'b3/B3CheckSpecial.cpp',
 """                            jit.setCarry(scratchGPR);
                            jit.lshift32(CCallHelpers::TrustedImm32(31), scratchGPR);""",
 """                            // PPC64 may not read XER -- mcrxrx is ISA 3.0 and
                            // this port's floor is POWER8 -- so setCarry() is a
                            // typed refusal there. It is also not needed on this
                            // path. The add that overflowed was x + x, so its
                            // carry out is bit 31 of x; and signed overflow of
                            // x + x means bit 31 of x differs from bit 31 of the
                            // result. The carry is therefore the complement of
                            // the result's sign bit, and the result is still in
                            // valueGPR. Same shape as setCarry: leave 0 or 1 in
                            // scratchGPR for the shift below.
                            if (isPPC64()) {
                                jit.move(valueGPR, scratchGPR);
                                jit.urshift32(CCallHelpers::TrustedImm32(31), scratchGPR);
                                jit.xor32(CCallHelpers::TrustedImm32(1), scratchGPR);
                            } else
                                jit.setCarry(scratchGPR);
                            jit.lshift32(CCallHelpers::TrustedImm32(31), scratchGPR);"""),

('REPLACE', J + 'b3/B3CheckSpecial.cpp',
 """                            jit.setCarry(scratchGPR);
                            jit.lshift64(CCallHelpers::TrustedImm32(63), scratchGPR);""",
 """                            // As the 32-bit case above: carry out of x + x is
                            // bit 63 of x, and signed overflow makes that the
                            // complement of the result's sign bit.
                            if (isPPC64()) {
                                jit.move(valueGPR, scratchGPR);
                                jit.urshift64(CCallHelpers::TrustedImm32(63), scratchGPR);
                                jit.xor64(CCallHelpers::TrustedImm32(1), scratchGPR);
                            } else
                                jit.setCarry(scratchGPR);
                            jit.lshift64(CCallHelpers::TrustedImm32(63), scratchGPR);"""),

# --- b3/air/AirCCallingConvention.cpp -----------------------------------
('REPLACE', J + 'b3/air/AirCCallingConvention.cpp',
 """        if (type == Float)
            val = block->appendNew<Value>(procedure, Trunc, Origin(), val);""",
 """        if (type == Float) {
            // ELFv2 hands a float argument over in DOUBLE format, so the
            // narrowing is a real conversion here, not a re-typing. Trunc is
            // bitwise -- B3LowerToAir lowers it to nothing at all, asserting
            // tmp(child) == tmp(value) -- so it would read word 1 of that
            // double and turn an incoming 1.0f into 0.0f.
            //
            // No isWasm() gate on this side: this function is only reached
            // through computeCCallArguments/cCallArgumentValues, which are
            // definitionally the C ABI and have no caller anywhere outside
            // testb3. OMG builds its own F32 prologue with ArgumentRegValue +
            // Trunc and does not come through here, which is correct under the
            // wasm raw-bits convention.
            val = block->appendNew<Value>(procedure, isPPC64() ? DoubleToFloat : Trunc, Origin(), val);
        }"""),

('REPLACE', J + 'b3/air/AirCCallingConvention.cpp',
 """    unsigned fpArgumentCount = 0;
    Value::OffsetType stackOffset = 0;

    for (auto type : types) {
        argUnderlyingCounts.append(underlyingArgs.size());""",
 """    unsigned fpArgumentCount = 0;
    NativeArgumentCursor cursor;
    Value::OffsetType stackOffset = 0;

    for (auto type : types) {
        argUnderlyingCounts.append(underlyingArgs.size());"""),

# The two ARM_THUMB2 call sites take the cursor too. They are preprocessed
# out on this target, but the signature is shared: leaving them would break a
# 32-bit ARM build of the same tree.
('REPLACE*2', J + 'b3/air/AirCCallingConvention.cpp',
 '            marshallCCallArgument(underlyingArgs, gpArgumentCount, fpArgumentCount, stackOffset, Int32);',
 '            marshallCCallArgument(underlyingArgs, gpArgumentCount, fpArgumentCount, cursor, stackOffset, Int32);'),

('REPLACE', J + 'b3/air/AirCCallingConvention.cpp',
 '        marshallCCallArgument(underlyingArgs, gpArgumentCount, fpArgumentCount, stackOffset, type);',
 '        marshallCCallArgument(underlyingArgs, gpArgumentCount, fpArgumentCount, cursor, stackOffset, type);'),

# --- b3/air/opcode_generator.rb -----------------------------------------
# The generator has to know the tag or AirOpcode.opcodes will not parse. Only
# this file's Index case went away upstream (it already threads the opcode);
# these are still the port's.
('REPLACE', J + 'b3/air/opcode_generator.rb',
 '    token =~ /\\A((x86)|(x86_32)|(x86_64_avx)|(x86_64)|(arm)|(armv7)|(arm64e)|(arm64_lse)|(arm64_sha3)|(arm64)|(32)|(64))\\Z/',
 '    token =~ /\\A((x86)|(x86_32)|(x86_64_avx)|(x86_64)|(arm)|(armv7)|(arm64e)|(arm64_lse)|(arm64_sha3)|(arm64)|(ppc64)|(32)|(64))\\Z/'),

('AFTER', J + 'b3/air/opcode_generator.rb',
 '            when "arm64_sha3"\n                result << "ARM64_SHA3"',
 '            when "ppc64"\n                result << "PPC64"'),

# --- runtime/Options.cpp -------------------------------------------------
# NOTE: the comments the port's own patch carried here were written before
# BBQ and OMG worked on this target and said so ("there is no BBQ and no OMG
# here"). They are rewritten rather than forward-ported: both tiers run now,
# wasm SIMD passes 61/61, and IPInt has a PPC64 arm throughout.
#
# Upstream has meanwhile started guarding the BBQ force-off with
# !CPU(ARM_THUMB2) for the same reason, so that line just gains a second
# architecture.
('REPLACE', J + 'runtime/Options.cpp',
 """#if !CPU(X86_64) && !CPU(ARM64)
    Options::useConcurrentGC() = false;
    Options::forceUnlinkedDFG() = false;
    Options::useWasmSIMD() = false;
    Options::useWasmIPInt() = false;
#if !CPU(ARM_THUMB2)
    Options::useBBQJIT() = false;
#endif
#endif""",
 """#if !CPU(X86_64) && !CPU(ARM64)
    Options::useConcurrentGC() = false;
    Options::forceUnlinkedDFG() = false;
#if !CPU(PPC64LE)
    // ppc64le keeps both of these. IPInt has a PPC64 arm throughout
    // llint/InPlaceInterpreter64.asm and offlineasm/ppc64.rb lowers the
    // vector register class its ipint_simd_* handlers use; wasm SIMD is
    // implemented in all three tiers here. The lane-order facts this depends
    // on and the correctness traps (min/max NaN, saturating conversions,
    // swizzle out of range) are in
    // powerpc64le-handbook/docs/jsc-ppc64le-wasm-simd.md.
    Options::useWasmSIMD() = false;
    Options::useWasmIPInt() = false;
#endif
#if !CPU(ARM_THUMB2) && !CPU(PPC64LE)
    // The other targets reaching this branch have no compiling wasm tier, so
    // IPInt is the only one and BBQ has to be refused. ppc64le is not one of
    // them: BBQ and OMG both run here and are left at their shared defaults,
    // which the compile-time check below makes safe.
    Options::useBBQJIT() = false;
#endif
#endif

    // THE RUNTIME MUST NOT CLAIM A TIER THE BUILD DOES NOT CONTAIN.
    //
    // useBBQJIT and useOMGJIT default to true in OptionsList.h unconditionally,
    // which is fine on targets where ENABLE_WEBASSEMBLY implies both. It is not
    // fine where they can be configured off independently: cmake defines
    // ENABLE_WEBASSEMBLY_BBQJIT and ENABLE_WEBASSEMBLY_OMGJIT from
    // ENABLE_FTL_DEFAULT, so passing -DENABLE_FTL_JIT=ON on the command line
    // leaves both OFF -- their default was already evaluated.
    //
    // A binary built that way reported useBBQJIT=true and useOMGJIT=true with
    // neither tier compiled in, and nine wasm tests then hung at tier-up: the
    // counter fires, the tier it names is not there, and nothing makes
    // progress. They did not fail, they ran for 900 seconds. Making the
    // options agree with the build turns that into an IPInt-only run, which is
    // slower and correct instead of fast and stuck.
#if !ENABLE(WEBASSEMBLY_BBQJIT)
    Options::useBBQJIT() = false;
#endif
#if !ENABLE(WEBASSEMBLY_OMGJIT)
    Options::useOMGJIT() = false;
#endif"""),

# --- wasm/js/JSToWasm.cpp ------------------------------------------------
# Eight wasm argument GPRs (r3-r10), and no loadPair64/storePair64 here. The
# USE(JSVALUE64) arm below is the six-register one, so taking it would leave
# r9/r10 holding whatever the wrapper last put there for a function with
# seven or eight integer parameters.
('BEFORE', J + 'wasm/js/JSToWasm.cpp',
 """#elif USE(JSVALUE64)
        jit.load64(CCallHelpers::Address(CCallHelpers::stackPointerRegister, 0 * 8), GPRInfo::regWA0);""",
 """#elif CPU(PPC64LE)
        jit.load64(CCallHelpers::Address(CCallHelpers::stackPointerRegister, 0 * 8), GPRInfo::regWA0);
        jit.load64(CCallHelpers::Address(CCallHelpers::stackPointerRegister, 1 * 8), GPRInfo::regWA1);
        jit.load64(CCallHelpers::Address(CCallHelpers::stackPointerRegister, 2 * 8), GPRInfo::regWA2);
        jit.load64(CCallHelpers::Address(CCallHelpers::stackPointerRegister, 3 * 8), GPRInfo::regWA3);
        jit.load64(CCallHelpers::Address(CCallHelpers::stackPointerRegister, 4 * 8), GPRInfo::regWA4);
        jit.load64(CCallHelpers::Address(CCallHelpers::stackPointerRegister, 5 * 8), GPRInfo::regWA5);
        jit.load64(CCallHelpers::Address(CCallHelpers::stackPointerRegister, 6 * 8), GPRInfo::regWA6);
        jit.load64(CCallHelpers::Address(CCallHelpers::stackPointerRegister, 7 * 8), GPRInfo::regWA7);"""),

('BEFORE', J + 'wasm/js/JSToWasm.cpp',
 """#elif USE(JSVALUE64)
        jit.store64(GPRInfo::regWA0, CCallHelpers::Address(CCallHelpers::stackPointerRegister, 0 * 8));""",
 """#elif CPU(PPC64LE)
        jit.store64(GPRInfo::regWA0, CCallHelpers::Address(CCallHelpers::stackPointerRegister, 0 * 8));
        jit.store64(GPRInfo::regWA1, CCallHelpers::Address(CCallHelpers::stackPointerRegister, 1 * 8));
        jit.store64(GPRInfo::regWA2, CCallHelpers::Address(CCallHelpers::stackPointerRegister, 2 * 8));
        jit.store64(GPRInfo::regWA3, CCallHelpers::Address(CCallHelpers::stackPointerRegister, 3 * 8));
        jit.store64(GPRInfo::regWA4, CCallHelpers::Address(CCallHelpers::stackPointerRegister, 4 * 8));
        jit.store64(GPRInfo::regWA5, CCallHelpers::Address(CCallHelpers::stackPointerRegister, 5 * 8));
        jit.store64(GPRInfo::regWA6, CCallHelpers::Address(CCallHelpers::stackPointerRegister, 6 * 8));
        jit.store64(GPRInfo::regWA7, CCallHelpers::Address(CCallHelpers::stackPointerRegister, 7 * 8));"""),

# --- b3/B3LowerMacros.cpp ------------------------------------------------
('REPLACE', J + 'b3/B3LowerMacros.cpp',
 """                if (isARM64()) {
                    Value* divResult = m_insertionSet.insert<Value>(m_index, UDiv, m_origin, m_value->child(0), m_value->child(1));""",
 """                // Same as Mod below: no integer modulo before ISA 3.0.
                if (isARM64() || isPPC64()) {
                    Value* divResult = m_insertionSet.insert<Value>(m_index, UDiv, m_origin, m_value->child(0), m_value->child(1));"""),

('REPLACE', J + 'b3/B3LowerMacros.cpp',
 """                if (isX86() || isARM_THUMB2()) {
                    bool isMax = m_value->opcode() == FMax;""",
 """                // PPC64 takes the x86 expansion rather than ARM64's native
                // fmin/fmax. It is pure B3 -- Equal, LessThan, GreaterThan,
                // BitAnd/BitOr for the signed-zero case and Add to propagate a
                // NaN -- so nothing here is x86-specific, and B3LowerToAir's
                // FMin/FMax arms are RELEASE_ASSERT(isARM64()) with
                // FloatMin/FloatMax tagged arm64-only.
                //
                // The alternative would be VSX xsmaxdp/xsmindp, and it was not
                // taken: their NaN and signed-zero behaviour is not JS's, the
                // ISA 3.0 xsmaxcdp/xsmincdp would need a hasISA30() gate
                // against the POWER8 floor, and this expansion settles both
                // cases explicitly rather than inheriting them from hardware.
                if (isX86() || isARM_THUMB2() || isPPC64()) {
                    bool isMax = m_value->opcode() == FMax;"""),

('REPLACE', J + 'b3/B3LowerMacros.cpp',
 """        Value* innerResult;
        if (isARM_THUMB2() && (m_value->type() == Int64 || m_value->type() == Int32))
            innerResult = callDivModHelper(normalDivCase, nonChillOpcode, num, den);
        else
            innerResult = normalDivCase->appendNew<Value>(m_proc, nonChillOpcode, m_origin, num, den);""",
 """        Value* innerResult;
        if (isARM_THUMB2() && (m_value->type() == Int64 || m_value->type() == Int32))
            innerResult = callDivModHelper(normalDivCase, nonChillOpcode, num, den);
        else if (nonChillOpcode == Mod && isPPC64()) {
            // PPC64 has divw/divd but no integer modulo before ISA 3.0, and
            // modud/modsd are POWER9-only -- a hot-path ISA 3.0 gate that
            // power8-baseline-power9-paths.md says has to be exercised both
            // ways to be real. So synthesise it, here rather than in the
            // caller: the branch above has already established that den + 1 is
            // above 1 unsigned, i.e. den is neither 0 nor -1, so this Div needs
            // no chill of its own and INT_MIN / -1 cannot arise. Emitting it in
            // this block is also what keeps it reachable -- the main loop never
            // revisits a block this pass inserts.
            Value* divResult = normalDivCase->appendNew<Value>(m_proc, Div, m_origin, num, den);
            Value* multipliedBack = normalDivCase->appendNew<Value>(m_proc, Mul, m_origin, divResult, den);
            innerResult = normalDivCase->appendNew<Value>(m_proc, Sub, m_origin, num, multipliedBack);
        } else
            innerResult = normalDivCase->appendNew<Value>(m_proc, nonChillOpcode, m_origin, num, den);"""),

# --- jit/CallFrameShuffler.cpp -------------------------------------------
('REPLACE', J + 'jit/CallFrameShuffler.cpp',
 """#elif CPU(ARM64) || CPU(RISCV64)
    // We load the frame pointer and link register manually. We
    // could ask the algorithm to load the link register for us
    // (which would allow for its use as an extra temporary), but
    // since its not in GPRInfo, we can't do it.""",
 """#elif CPU(ARM64) || CPU(RISCV64) || CPU(PPC64LE)
    // We load the frame pointer and link register manually. We
    // could ask the algorithm to load the link register for us
    // (which would allow for its use as an extra temporary), but
    // since its not in GPRInfo, we can't do it.
    //
    // On PPC64 the link register is not merely absent from GPRInfo, it is an
    // SPR; `loadToLinkRegister` below is the mflr/mtlr-shaped equivalent of
    // the ARM64 load. The frame is the same shape either way, because
    // `pushFramePointerAndLinkRegister` builds exactly the ARM64 pair."""),

('REPLACE', J + 'jit/CallFrameShuffler.cpp',
 """#if CPU(ARM_THUMB2) || CPU(ARM64) || CPU(RISCV64)
    m_jit.loadPtr(MacroAssembler::Address(MacroAssembler::framePointerRegister, CallFrame::returnPCOffset()),
        MacroAssembler::linkRegister);""",
 """#if CPU(PPC64LE)
    m_jit.loadToLinkRegister(MacroAssembler::Address(MacroAssembler::framePointerRegister, CallFrame::returnPCOffset()));
#elif CPU(ARM_THUMB2) || CPU(ARM64) || CPU(RISCV64)
    m_jit.loadPtr(MacroAssembler::Address(MacroAssembler::framePointerRegister, CallFrame::returnPCOffset()),
        MacroAssembler::linkRegister);"""),

# --- jit/AssemblyHelpers.cpp ---------------------------------------------
# The Bun fork brackets this call with pushPair/popPair for ARM64 and RISCV64;
# WebKitGTK has no such save, so only the ppc64 arm is carried over.
('BEFORE', J + 'jit/AssemblyHelpers.cpp',
 """    // Set up one argument.
    move(TrustedImmPtr(&vm), GPRInfo::argumentGPR0);""",
 """    // An exception check can be emitted where the caller still holds its
    // return address in the link register -- a CTI thunk that has not built
    // its frame yet -- and the call below would destroy it. PowerPC's link
    // register is an SPR, so it is saved the way the port's prologue saves it.
    //
    // Upstream has no such save on ARM64 either, where blr clobbers x30 in
    // exactly the same way. That is left alone rather than "fixed" here: it is
    // reachable only under --useExceptionFuzz and cannot be tested from this
    // target.
#if CPU(PPC64LE)
    pushFramePointerAndLinkRegister();
#endif
"""),

('AFTER', J + 'jit/AssemblyHelpers.cpp',
 '    call(GPRInfo::nonPreservedNonReturnGPR, OperationPtrTag);',
 """#if CPU(PPC64LE)
    popFramePointerAndLinkRegister();
#endif"""),

# --- wasm/WasmBBQJIT.cpp -------------------------------------------------
('REPLACE', J + 'wasm/WasmBBQJIT.cpp',
 """#elif CPU(ARM64) || CPU(ARM_THUMB2)
    m_jit.loadPairPtr(MacroAssembler::framePointerRegister, callerFramePointer, MacroAssembler::linkRegister);
#else
    UNUSED_PARAM(callerFramePointer);
    UNREACHABLE_FOR_PLATFORM();""",
 """#elif CPU(ARM64) || CPU(ARM_THUMB2)
    m_jit.loadPairPtr(MacroAssembler::framePointerRegister, callerFramePointer, MacroAssembler::linkRegister);
#elif CPU(PPC64LE)
    // The frame shape is ARM64's -- [cfr + 0] CallerFrame, [cfr + 8] ReturnPC,
    // which is what pushFramePointerAndLinkRegister builds so that JIT frames
    // and the LLInt's agree. What differs is that this target has no
    // linkRegister GPR: LR is a special register, so the return address goes
    // straight there and the two loads cannot be paired.
    //
    // Writing LR this early is safe, and that is a property of the transfer
    // rather than an accident. Everything between here and it is register and
    // stack movement, and BOTH transfers preserve LR: farJump lowers to
    // mtctr/bctr (emitIndirectJump), and nearTailCall emits
    // unlinkedBranchInsn(false) -- a plain branch, not a branch-and-link. If
    // either ever became a linking branch this would have to move to just
    // before the jump.
    m_jit.loadPtr(Address(MacroAssembler::framePointerRegister), callerFramePointer);
    m_jit.loadToLinkRegister(Address(MacroAssembler::framePointerRegister, sizeof(Register)));
#else
    UNUSED_PARAM(callerFramePointer);
    UNREACHABLE_FOR_PLATFORM();"""),

('REPLACE', J + 'wasm/WasmBBQJIT.cpp',
 """#elif CPU(ARM64) || CPU(ARM_THUMB2)
    m_jit.addPtr(TrustedImm32(tailCallStackOffsetFromFP + Checked<int>(sizeof(CallerFrameAndPC))), MacroAssembler::framePointerRegister, MacroAssembler::stackPointerRegister);
    m_jit.move(callerFramePointer, MacroAssembler::framePointerRegister);""",
 """#elif CPU(ARM64) || CPU(ARM_THUMB2) || CPU(PPC64LE)
    m_jit.addPtr(TrustedImm32(tailCallStackOffsetFromFP + Checked<int>(sizeof(CallerFrameAndPC))), MacroAssembler::framePointerRegister, MacroAssembler::stackPointerRegister);
    m_jit.move(callerFramePointer, MacroAssembler::framePointerRegister);"""),

# --- wasm/WasmBBQJIT64.cpp -----------------------------------------------
('REPLACE', J + 'wasm/WasmBBQJIT64.cpp',
 """#elif CPU(ARM64)
    if (resultHiLocation.asGPR() == lhsLocation.asGPR()) {
        m_jit.move(lhsLocation.asGPR(), wasmScratchGPR);
        m_jit.uMulHigh64(wasmScratchGPR, rhsLocation.asGPR(), resultHiLocation.asGPR());""",
 """#elif CPU(ARM64) || CPU(PPC64LE)
    // mulhdu then mulld, and the aliasing dance matters for the same reason it
    // does on ARM64: the high product is written first, so its destination
    // must not be an input the low product still needs.
    if (resultHiLocation.asGPR() == lhsLocation.asGPR()) {
        m_jit.move(lhsLocation.asGPR(), wasmScratchGPR);
        m_jit.uMulHigh64(wasmScratchGPR, rhsLocation.asGPR(), resultHiLocation.asGPR());"""),

('REPLACE', J + 'wasm/WasmBBQJIT64.cpp',
 """#elif CPU(ARM64)
    if (resultHiLocation.asGPR() == lhsLocation.asGPR()) {
        m_jit.move(lhsLocation.asGPR(), wasmScratchGPR);
        m_jit.mulHigh64(wasmScratchGPR, rhsLocation.asGPR(), resultHiLocation.asGPR());""",
 """#elif CPU(ARM64) || CPU(PPC64LE)
    // mulhd then mulld; same aliasing rule as the unsigned form above.
    if (resultHiLocation.asGPR() == lhsLocation.asGPR()) {
        m_jit.move(lhsLocation.asGPR(), wasmScratchGPR);
        m_jit.mulHigh64(wasmScratchGPR, rhsLocation.asGPR(), resultHiLocation.asGPR());"""),

# --- wasm/WasmOMGIRGenerator.cpp ----------------------------------------
# Probe::Context::vector() exists only where the probe saves whole vectors.
('REPLACE', J + 'wasm/WasmOMGIRGenerator.cpp',
 """                    else if (src.isFPR())
                        dataLog(context.vector(src.fpr()));""",
 """                    else if (src.isFPR()) {
#if CPU(X86_64) || CPU(ARM64)
                        dataLog(context.vector(src.fpr()));
#else
                        dataLog("<v128: this target's probe captures 64 bits of an FPR>");
#endif
                    }"""),

('REPLACE', J + 'wasm/WasmOMGIRGenerator.cpp',
 """                    else if (arg.location.isFPR())
                        dataLog(context.vector(arg.location.fpr()));""",
 """                    else if (arg.location.isFPR()) {
#if CPU(X86_64) || CPU(ARM64)
                        dataLog(context.vector(arg.location.fpr()));
#else
                        dataLog("<v128: this target's probe captures 64 bits of an FPR>");
#endif
                    }"""),

# --- llint/InPlaceInterpreter.asm ---------------------------------------
('REPLACE', J + 'llint/InPlaceInterpreter.asm',
 'if X86_64 or ARM64 or ARM64E or RISCV64',
 'if X86_64 or ARM64 or ARM64E or RISCV64 or PPC64'),

('REPLACE', J + 'llint/InPlaceInterpreter.asm',
 'elsif ARM64 or ARM64E or RISCV64',
 'elsif ARM64 or ARM64E or RISCV64 or PPC64'),

('REPLACE', J + 'llint/InPlaceInterpreter.asm',
 """macro forEachWasmArgumentGPR(fn)
    if ARM64 or ARM64E""",
 """macro forEachWasmArgumentGPR(fn)
    if ARM64 or ARM64E or PPC64"""),

('REPLACE', J + 'llint/InPlaceInterpreter.asm',
 '    call ws0, WasmEntryPtrTag',
 """    if PPC64
        # Generated code, and ws0 is already r12, the ELFv2 indirect
        # call register, so this is a bare bctrl.
        ppc64JSCall ws0
    else
        call ws0, WasmEntryPtrTag
    end"""),

# Six guards, all the same, all needing the same architecture added. Upstream
# has since added ARMv7 to each; the two that already name PPC64 came through
# the patch series and are not matched here.
('REPLACE*6', J + 'llint/InPlaceInterpreter.asm',
 'if WEBASSEMBLY and (ARM64 or ARM64E or X86_64 or ARMv7)',
 'if WEBASSEMBLY and (ARM64 or ARM64E or X86_64 or ARMv7 or PPC64)'),

('REPLACE', J + 'llint/InPlaceInterpreter.asm',
 """if JSVALUE64 and (ARM64 or ARM64E or X86_64)
    include InPlaceInterpreter64""",
 """if JSVALUE64 and (ARM64 or ARM64E or X86_64 or PPC64)
    include InPlaceInterpreter64"""),

# --- yarr/YarrJIT.cpp ----------------------------------------------------
# The port's two hunks around `maxLoadBits` are not represented here: that
# construct exists only in the Bun fork (four mentions there, none anywhere in
# 2.54.1), so there is nothing to widen.
('REPLACE', J + 'yarr/YarrJIT.cpp',
 """#if CPU(X86_64) || CPU(ARM64) || CPU(RISCV64)
                auto check8 = [&] (Checked<unsigned> offset, uint64_t characters, uint64_t caseMask, uint64_t ignoredCharsMask, MatchTargets& matchTargets) {""",
 """#if CPU(X86_64) || CPU(ARM64) || CPU(RISCV64) || CPU(PPC64LE)
                auto check8 = [&] (Checked<unsigned> offset, uint64_t characters, uint64_t caseMask, uint64_t ignoredCharsMask, MatchTargets& matchTargets) {"""),

('REPLACE', J + 'yarr/YarrJIT.cpp',
 """#if CPU(X86_64) || CPU(ARM64) || CPU(RISCV64)
                auto check4 = [&] (Checked<unsigned> offset, uint64_t characters, uint64_t caseMask, uint64_t ignoredCharsMask, MatchTargets& matchTargets) {""",
 """#if CPU(X86_64) || CPU(ARM64) || CPU(RISCV64) || CPU(PPC64LE)
                auto check4 = [&] (Checked<unsigned> offset, uint64_t characters, uint64_t caseMask, uint64_t ignoredCharsMask, MatchTargets& matchTargets) {"""),

('REPLACE', J + 'yarr/YarrJIT.cpp',
 """#if CPU(ARM64) || CPU(RISCV64)
        static_assert(sizeof(BoyerMooreBitmap::Map::WordType) == sizeof(uint64_t));""",
 """#if CPU(ARM64) || CPU(RISCV64) || CPU(PPC64LE)
        static_assert(sizeof(BoyerMooreBitmap::Map::WordType) == sizeof(uint64_t));"""),

('REPLACE', J + 'yarr/YarrJIT.cpp',
 """#elif CPU(RISCV64)
#endif
        return registers;""",
 """#elif CPU(RISCV64)
#elif CPU(PPC64LE)
        // r29 and r30 are this port's MacroAssembler temporaries and are
        // ELFv2-nonvolatile, so any generated code entered from C -- which a
        // compiled regex is -- must save them. Every pattern needs them:
        // materialising a constant for a character comparison goes through
        // one.
        registers.add(PPC64Registers::r29, IgnoreVectors);
        registers.add(PPC64Registers::r30, IgnoreVectors);

        // The three unicode/duplicate-named-group roles, on x86_64's
        // condition for its r13-r15 widened by the duplicate named group
        // case, which is where unicodeAndSubpatternIdTemp is used.
        // matchingContext and remainingMatchCount are volatile here, so the
        // m_containsNestedSubpatterns arm x86_64 needs has no counterpart.
        if (mayCall() || m_callFrameSizeInBytes || m_pattern.hasDuplicateNamedCaptureGroups()) {
            registers.add(PPC64Registers::r25, IgnoreVectors); // regUnicodeInputAndTrail
            registers.add(PPC64Registers::r26, IgnoreVectors); // unicodeAndSubpatternIdTemp
            registers.add(PPC64Registers::r27, IgnoreVectors); // endOfStringAddress
        }
#endif
        return registers;"""),

('REPLACE', J + 'yarr/YarrJIT.cpp',
 """#if CPU(X86_64) || CPU(ARM_THUMB2) || CPU(RISCV64)
        m_jit.emitFunctionPrologue();""",
 """        // PPC64 takes the unconditional arm: the prologue is what saves the
        // link register and r31, so unlike ARM64 it is never skippable.
#if CPU(X86_64) || CPU(ARM_THUMB2) || CPU(RISCV64) || CPU(PPC64LE)
        m_jit.emitFunctionPrologue();"""),

('REPLACE', J + 'yarr/YarrJIT.cpp',
 """#if CPU(X86_64) || CPU(ARM_THUMB2) || CPU(RISCV64)
        m_jit.emitFunctionEpilogue();""",
 """#if CPU(X86_64) || CPU(ARM_THUMB2) || CPU(RISCV64) || CPU(PPC64LE)
        m_jit.emitFunctionEpilogue();"""),

# --- b3/air/AirArg.h : an UPSTREAM bug, not a port edit ------------------
# isValidFPImm64Form declares `u64` only inside its CPU(ARM64)/CPU(X86_64)
# arms and then uses it unconditionally below, so 2.54.1 does not compile on
# any third architecture. The early `if (!isARM64() && !isX86_64())` is a
# RUN-time guard; the code below it still has to compile. Hoisting the
# declaration above the fork fixes it and changes nothing for ARM64 or x86-64.
# Delete this entry when upstream fixes it.
('REPLACE', J + 'b3/air/AirArg.h',
 """#if CPU(ARM64)
        if (ARM64Assembler::canEncodeFPImm<64>(value))
            return true;

        uint64_t u64 = static_cast<uint64_t>(value);
        if (ARM64FPImmediate::create64(u64).isValid())
            return true;

#elif CPU(X86_64)
        uint64_t u64 = static_cast<uint64_t>(value);

        if (u64 == 0xFFFFFFFFFFFFFFFFULL)""",
 """        uint64_t u64 = static_cast<uint64_t>(value);

#if CPU(ARM64)
        if (ARM64Assembler::canEncodeFPImm<64>(value))
            return true;

        if (ARM64FPImmediate::create64(u64).isValid())
            return true;

#elif CPU(X86_64)
        if (u64 == 0xFFFFFFFFFFFFFFFFULL)"""),

# --- lol/LOLJIT.cpp -----------------------------------------------------
# LOL is new upstream code the port had never seen; 2.54.1 ends its
# architecture fork in `#error "Unsupported Architecture"`.
('REPLACE', J + 'lol/LOLJIT.cpp',
 """#if CPU(X86_64)
        pop(GPRInfo::argumentGPR1);
#else
        tagPtr(NoPtrTag, linkRegister);""",
 """#if CPU(X86_64)
        pop(GPRInfo::argumentGPR1);
#elif CPU(PPC64LE)
        // The link register is an SPR here, so the return address is read
        // out with mflr rather than moved from a named GPR. There is no
        // pointer authentication to tag.
        moveFromLinkRegister(GPRInfo::argumentGPR1);
#else
        tagPtr(NoPtrTag, linkRegister);"""),

('REPLACE', J + 'lol/LOLJIT.cpp',
 """#if CPU(X86_64)
        push(GPRInfo::argumentGPR1);
#else
        move(GPRInfo::argumentGPR1, linkRegister);""",
 """#if CPU(X86_64)
        push(GPRInfo::argumentGPR1);
#elif CPU(PPC64LE)
        moveToLinkRegister(GPRInfo::argumentGPR1);
#else
        move(GPRInfo::argumentGPR1, linkRegister);"""),

('REPLACE', J + 'lol/LOLJIT.cpp',
 """#elif CPU(ARM64)

void LOLJIT::emit_op_mod(const JSInstruction* currentInstruction)""",
 """#elif CPU(ARM64) || CPU(PPC64LE)

void LOLJIT::emit_op_mod(const JSInstruction* currentInstruction)"""),

# The DEFINITION's guard, which must track the declaration's in AssemblyHelpers.h
# or the OMG stack-overflow check links against nothing. Upstream widened this
# one with CPU(ARM) rather than CPU(ARM_THUMB2); both are kept.
('REPLACE', J + 'jit/AssemblyHelpers.cpp',
 """#if CPU(ARM64) || CPU(X86_64) || CPU(RISCV64) || CPU(ARM)
AssemblyHelpers::JumpList AssemblyHelpers::checkWasmStackOverflow(GPRReg instanceGPR, TrustedImm32 checkSize, GPRReg framePointerGPR)""",
 """#if CPU(ARM64) || CPU(X86_64) || CPU(RISCV64) || CPU(ARM) || CPU(PPC64LE)
AssemblyHelpers::JumpList AssemblyHelpers::checkWasmStackOverflow(GPRReg instanceGPR, TrustedImm32 checkSize, GPRReg framePointerGPR)"""),

# --- llint/LowLevelInterpreter.asm : functionPrologue / functionEpilogue ---
# THE one that mattered. Without the PPC64 arm these emit NOTHING on this
# target: no saved link register, no frame. The interpreter then returns to
# whatever LR happened to hold, so a call lands on address 0 or on bytes from
# .rodata, and a branch appears to loop. It hid from every gate because the
# replacement line is textually identical to one in preserveCallerPCAndCFR,
# which DID get patched -- so "are the added lines present in the file" said
# yes while this site was untouched.
('REPLACE', J + 'llint/LowLevelInterpreter.asm',
 """macro functionPrologue()
    tagReturnAddress sp
    if X86_64
        push cfr
    elsif ARM64 or ARM64E or RISCV64
        push cfr, lr""",
 """macro functionPrologue()
    tagReturnAddress sp
    if X86_64
        push cfr
    elsif ARM64 or ARM64E or RISCV64 or PPC64
        push cfr, lr"""),

('REPLACE', J + 'llint/LowLevelInterpreter.asm',
 """macro functionEpilogue()
    if X86_64
        pop cfr
    elsif ARM64 or ARM64E or RISCV64
        pop lr, cfr""",
 """macro functionEpilogue()
    if X86_64
        pop cfr
    elsif ARM64 or ARM64E or RISCV64 or PPC64
        pop lr, cfr"""),

# The VM-entry callee-save copies, used on exception unwind. Same bug class as
# functionPrologue above: no ppc64 arm meant they emitted nothing, so the
# callee saves were never recorded. The RISCV64 arm is slot-for-slot what this
# port needs -- csr0-csr10 plus csfr0-csfr11, 23 stores, which is exactly
# NUMBER_OF_CALLEE_SAVES_REGISTERS -- so it is shared rather than duplicated.
('REPLACE', J + 'llint/LowLevelInterpreter.asm',
 """    elsif RISCV64
        storep csr0, [buffer]""",
 """    elsif RISCV64 or PPC64
        storep csr0, [buffer]"""),

('REPLACE', J + 'llint/LowLevelInterpreter.asm',
 """    elsif RISCV64
        loadq [buffer], csr0""",
 """    elsif RISCV64 or PPC64
        loadq [buffer], csr0"""),

]


# Hunks from the port's patch series that are deliberately NOT carried forward
# to this WebKit version, with the reason. Each one is a place the port got
# smaller: keeping them would mean re-adding something upstream has already
# done, or re-adding something upstream has removed the need for.
OBSOLETE = {
    'Source/JavaScriptCore/wasm/WasmFunctionParser.h':
        "lifts the ENABLE(B3_JIT) gate off the ExtSIMD parse case so wasm SIMD "
        "parses in a build without B3. Not carried forward because this "
        "package enables FTL, which enables B3_JIT, so the gate is already "
        "satisfied and SIMD works (verified: a wasm module runs 200k calls "
        "correctly). Re-apply if a CLoop or FTL-off ppc64le build is ever "
        "packaged. Upstream has meanwhile added the ENABLE(WEBASSEMBLY_OMGJIT) "
        "guard this hunk's second half wanted, at its other two call sites.",
    'Source/JavaScriptCore/ftl/FTLLowerDFGToB3.cpp':
        "all three hunks are inapplicable to WebKitGTK: two are Bun's CallFFI "
        "lowering (no CallFFI or FFI::Type anywhere in this tree) and the "
        "third is the ENABLE(YARR_JIT_REGEXP_TEST_INLINE) split, which "
        "upstream already has",
    'Source/JavaScriptCore/domjit/DOMJITEffect.h':
        "upstream restructured Effect: forReadKinds, isTop() and the reads[4]/"
        "writes[4] arrays this patch guarded with ENABLE(DFG_JIT) are all gone, "
        "so there is no DFG coupling left to guard",
    'Source/JavaScriptCore/dfg/DFGStrengthReductionPhase.cpp':
        "upstream guards both convertTestToTestInline and its call site with "
        "#if ENABLE(YARR_JIT_REGEXP_TEST_INLINE); an early return inside the "
        "lambda would be dead code nested inside the very guard that removes it",
    'Source/JavaScriptCore/dfg/DFGSpeculativeJIT64.cpp':
        "upstream already splits compileRegExpTestInline on "
        "ENABLE(YARR_JIT_REGEXP_TEST_INLINE) with its own #else stub, so the "
        "port only has to turn the feature off in PlatformEnable.h",
}


def enc(s):
    return s.replace('\\', '\\\\').replace('\n', '\\n').replace('|', '\\p')


if __name__ == '__main__':
    print('# Generated by tools/edits.py -- edit that, not this.')
    for kind, path, anchor, payload in EDITS:
        print('%s|%s|%s|%s' % (kind, path, enc(anchor), enc(payload)))
