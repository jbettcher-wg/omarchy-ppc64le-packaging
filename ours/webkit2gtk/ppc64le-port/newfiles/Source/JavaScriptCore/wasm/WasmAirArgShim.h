/*
 * Copyright (C) 2026 Jordan Bettcher. All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions
 * are met:
 * 1. Redistributions of source code must retain the above copyright
 *    notice, this list of conditions and the following disclaimer.
 * 2. Redistributions in binary form must reproduce the above copyright
 *    notice, this list of conditions and the following disclaimer in the
 *    documentation and/or other materials provided with the distribution.
 *
 * THIS SOFTWARE IS PROVIDED BY APPLE INC. ``AS IS'' AND ANY
 * EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 * IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
 * PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL APPLE INC. OR
 * CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
 * EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
 * PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
 * PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY
 * OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

#pragma once

#include <wtf/Platform.h>

#if ENABLE(WEBASSEMBLY)

#if ENABLE(B3_JIT)

#include "AirArg.h"

#else

// The wasm SIMD opcode table (WasmSIMDOpcodes.h, FOR_EACH_WASM_EXT_SIMD_REL_OP)
// carries the comparison each relational SIMD opcode means as a
// B3::Air::Arg, and FunctionParser::simd() takes one and hands it to
// Context::addSIMDRelOp(). That is the only reason the wasm *parser* has ever
// needed a B3 type, and AirArg.h is compiled only under ENABLE(B3_JIT), which
// in turn is defined only under FTL (PlatformEnable.h). So on a target whose
// only SIMD-capable tier is the in-place interpreter -- ppc64le, where
// IPIntGenerator::tierSupportsSIMD() is true and BBQ, OMG and FTL are all off
// -- the SIMD parser was unreachable for want of a value that no consumer in
// such a build ever reads: IPIntGenerator::addSIMDRelOp() ignores every
// argument and only adjusts the operand stack depth.
//
// Supply the value's shape rather than the whole of B3. This mirrors what
// WasmCompilationContext.h already does for B3::Procedure under the same
// condition. The condition is stored rather than discarded so the type is not
// degenerate and a non-B3 consumer could read it; nothing does today.
//
// Kept deliberately minimal: if a future tier on such a target needs more of
// Arg than the two condition constructors, that is a signal to build B3
// rather than to grow this file.

#include "MacroAssembler.h"

namespace JSC { namespace B3 { namespace Air {

class Arg {
public:
    enum Kind : int8_t {
        Invalid,
        RelCond,
        DoubleCond,
    };

    Arg() = default;

    static Arg relCond(MacroAssembler::RelationalCondition condition)
    {
        Arg result;
        result.m_kind = RelCond;
        result.m_value = condition;
        return result;
    }

    static Arg doubleCond(MacroAssembler::DoubleCondition condition)
    {
        Arg result;
        result.m_kind = DoubleCond;
        result.m_value = condition;
        return result;
    }

    Kind kind() const { return m_kind; }
    bool isRelCond() const { return m_kind == RelCond; }
    bool isDoubleCond() const { return m_kind == DoubleCond; }

    MacroAssembler::RelationalCondition asRelationalCondition() const
    {
        ASSERT(isRelCond());
        return static_cast<MacroAssembler::RelationalCondition>(m_value);
    }

    MacroAssembler::DoubleCondition asDoubleCondition() const
    {
        ASSERT(isDoubleCond());
        return static_cast<MacroAssembler::DoubleCondition>(m_value);
    }

private:
    Kind m_kind { Invalid };
    int64_t m_value { 0 };
};

} } } // namespace JSC::B3::Air

#endif // ENABLE(B3_JIT)

#endif // ENABLE(WEBASSEMBLY)
