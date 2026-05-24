from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

from .c_parser import (
    ArrayAccessExpr,
    ArrayInitializer,
    ArrayLValue,
    AssignStmt,
    BinaryExpr,
    BlockStmt,
    CallExpr,
    Expr,
    ExprStmt,
    FunctionDecl,
    GlobalDecl,
    IfStmt,
    NumberExpr,
    ParamDecl,
    Program,
    ReturnStmt,
    UnaryExpr,
    VarDeclStmt,
    VarExpr,
    VarLValue,
    WhileStmt,
    parse_program,
)


class CompileError(ValueError):
    pass


TEMP_COUNT = 16


def compile_source(source: str) -> str:
    program = parse_program(source)
    generator = CodeGenerator(program)
    return generator.compile()


@dataclass(frozen=True)
class FunctionContext:
    name: str
    return_type: str
    storage_labels: dict[str, str]


class CodeGenerator:
    def __init__(self, program: Program):
        self.program = program
        self.lines: list[str] = []
        self.globals: dict[str, GlobalDecl] = {}
        self.functions: dict[str, FunctionDecl] = {}
        self.function_params: dict[str, dict[str, str]] = {}
        self.function_locals: dict[str, dict[str, str]] = {}
        self.function_calls: dict[str, set[str]] = {}
        self.reachable_functions: tuple[str, ...] = ()
        self.label_counter = 0
        self.temp_depth = 0
        self.validate()

    def validate(self) -> None:
        for declaration in self.program.globals:
            if declaration.name in self.globals:
                raise CompileError(f"duplicate global declaration {declaration.name!r}")
            if declaration.array_size is not None and declaration.array_size <= 0:
                raise CompileError(f"array {declaration.name!r} must have a positive size")
            if declaration.array_size is not None and declaration.array_size > 256:
                raise CompileError(f"array {declaration.name!r} exceeds maximum supported size 256")
            if declaration.array_size is None and isinstance(declaration.initializer, ArrayInitializer):
                raise CompileError(f"scalar global {declaration.name!r} cannot use an array initializer")
            if declaration.array_size is not None and declaration.is_volatile:
                raise CompileError(f"volatile array {declaration.name!r} is not supported")
            if declaration.array_size is not None and declaration.initializer is not None:
                if not isinstance(declaration.initializer, ArrayInitializer):
                    raise CompileError(f"array {declaration.name!r} requires a brace initializer")
                if len(declaration.initializer.values) > declaration.array_size:
                    raise CompileError(
                        f"array initializer for {declaration.name!r} has "
                        f"{len(declaration.initializer.values)} values but size is {declaration.array_size}"
                    )
            self.globals[declaration.name] = declaration

        for function in self.program.functions:
            if function.name in self.functions:
                raise CompileError(f"duplicate function declaration {function.name!r}")
            if function.name in self.globals:
                raise CompileError(f"name {function.name!r} is used by both a global and a function")
            param_labels: dict[str, str] = {}
            for parameter in function.parameters:
                if parameter.type_name != "u8":
                    raise CompileError(
                        f"function parameter {parameter.name!r} in {function.name!r} "
                        f"must have type 'u8'"
                    )
                if parameter.name in param_labels:
                    raise CompileError(
                        f"duplicate parameter {parameter.name!r} inside function {function.name!r}"
                    )
                param_labels[parameter.name] = f"__{function.name}_arg_{parameter.name}"
            self.function_params[function.name] = param_labels
            self.functions[function.name] = function

        if "reset" not in self.functions:
            raise CompileError("program must define void reset(void)")

        for function in self.program.functions:
            local_labels: dict[str, str] = {}
            for name in self.collect_locals(function.body):
                if name in self.function_params[function.name]:
                    raise CompileError(
                        f"local {name!r} inside function {function.name!r} "
                        f"conflicts with a parameter"
                    )
                if name in local_labels:
                    raise CompileError(f"duplicate local {name!r} inside function {function.name!r}")
                local_labels[name] = f"__{function.name}_{name}"
            self.function_locals[function.name] = local_labels
            self.function_calls[function.name] = self.collect_calls_block(function.body)

        self.reachable_functions = self.compute_reachable_functions()

    def collect_locals(self, block: BlockStmt) -> list[str]:
        names: list[str] = []
        for statement in block.statements:
            if isinstance(statement, VarDeclStmt):
                names.append(statement.name)
            elif isinstance(statement, BlockStmt):
                names.extend(self.collect_locals(statement))
            elif isinstance(statement, IfStmt):
                names.extend(self.collect_locals(statement.then_block))
                if statement.else_block is not None:
                    names.extend(self.collect_locals(statement.else_block))
            elif isinstance(statement, WhileStmt):
                names.extend(self.collect_locals(statement.body))
        return names

    def collect_calls_block(self, block: BlockStmt) -> set[str]:
        calls: set[str] = set()
        for statement in block.statements:
            calls.update(self.collect_calls_statement(statement))
        return calls

    def collect_calls_statement(self, statement: object) -> set[str]:
        if isinstance(statement, BlockStmt):
            return self.collect_calls_block(statement)
        if isinstance(statement, VarDeclStmt):
            return set() if statement.initializer is None else self.collect_calls_expr(statement.initializer)
        if isinstance(statement, AssignStmt):
            calls = set()
            if isinstance(statement.target, ArrayLValue):
                calls.update(self.collect_calls_expr(statement.target.index))
            calls.update(self.collect_calls_expr(statement.value))
            return calls
        if isinstance(statement, ExprStmt):
            return self.collect_calls_expr(statement.expr)
        if isinstance(statement, ReturnStmt):
            return set() if statement.value is None else self.collect_calls_expr(statement.value)
        if isinstance(statement, IfStmt):
            calls = self.collect_calls_expr(statement.condition)
            calls.update(self.collect_calls_block(statement.then_block))
            if statement.else_block is not None:
                calls.update(self.collect_calls_block(statement.else_block))
            return calls
        if isinstance(statement, WhileStmt):
            calls = self.collect_calls_expr(statement.condition)
            calls.update(self.collect_calls_block(statement.body))
            return calls
        return set()

    def collect_calls_expr(self, expr: Expr) -> set[str]:
        if isinstance(expr, (NumberExpr, VarExpr)):
            return set()
        if isinstance(expr, ArrayAccessExpr):
            return self.collect_calls_expr(expr.index)
        if isinstance(expr, UnaryExpr):
            return self.collect_calls_expr(expr.operand)
        if isinstance(expr, BinaryExpr):
            calls = self.collect_calls_expr(expr.left)
            calls.update(self.collect_calls_expr(expr.right))
            return calls
        if isinstance(expr, CallExpr):
            calls = {expr.name}
            for argument in expr.args:
                calls.update(self.collect_calls_expr(argument))
            return calls
        raise CompileError(f"unsupported expression node {expr!r}")

    def compute_reachable_functions(self) -> tuple[str, ...]:
        roots = ["reset"]
        if "nmi" in self.functions:
            roots.append("nmi")
        if "irq" in self.functions:
            roots.append("irq")

        reachable: set[str] = set()
        pending = list(roots)
        while pending:
            name = pending.pop()
            if name in reachable:
                continue
            if name not in self.functions:
                raise CompileError(f"entry function {name!r} is not defined")
            reachable.add(name)
            for callee in self.function_calls.get(name, set()):
                if callee not in self.functions:
                    raise CompileError(f"call to unknown function {callee!r} from {name!r}")
                if callee not in reachable:
                    pending.append(callee)

        return tuple(function.name for function in self.program.functions if function.name in reachable)

    def compile(self) -> str:
        self.emit("; generated by nesc")
        self.emit('.segment "ZEROPAGE"')
        for index in range(TEMP_COUNT):
            self.emit(f"__tmp{index}: .res 1")
        self.emit("")

        self.emit('.segment "RAM"')
        for declaration in self.program.globals:
            if declaration.absolute_address is None:
                self.emit(f"{declaration.name}: .res {declaration.array_size or 1}")
        for function_name in self.reachable_functions:
            for param_label in self.function_params[function_name].values():
                self.emit(f"{param_label}: .res 1")
            for local_label in self.function_locals[function_name].values():
                self.emit(f"{local_label}: .res 1")
        self.emit("")

        self.emit('.segment "CODE"')
        self.emit("__reset_entry:")
        self.emit("  sei")
        self.emit("  cld")
        self.emit("  ldx #0xff")
        self.emit("  txs")
        for declaration in self.program.globals:
            self.emit_global_initializer(declaration)
        self.emit("  jsr reset")
        self.emit("__reset_hang:")
        self.emit("  jmp __reset_hang")
        self.emit("")

        self.emit("__nmi_entry:")
        if "nmi" in self.functions:
            self.emit("  jsr nmi")
        self.emit("  rti")
        self.emit("")

        self.emit("__irq_entry:")
        if "irq" in self.functions:
            self.emit("  jsr irq")
        self.emit("  rti")
        self.emit("")

        for function_name in self.reachable_functions:
            self.emit_function(self.functions[function_name])

        self.emit('.segment "VECTORS"')
        self.emit(".word __nmi_entry, __reset_entry, __irq_entry")
        self.emit("")
        return "\n".join(self.lines)

    def emit_function(self, function: FunctionDecl) -> None:
        storage_labels = dict(self.function_params[function.name])
        storage_labels.update(self.function_locals[function.name])
        context = FunctionContext(
            name=function.name,
            return_type=function.return_type,
            storage_labels=storage_labels,
        )
        self.emit(f"{function.name}:")
        self.emit_block(function.body, context)
        if function.return_type == "void":
            self.emit("  rts")
        else:
            self.emit("  lda #0x00")
            self.emit("  rts")
        self.emit("")

    def emit_block(self, block: BlockStmt, context: FunctionContext) -> None:
        for statement in block.statements:
            self.emit_statement(statement, context)

    def emit_statement(self, statement: object, context: FunctionContext) -> None:
        if isinstance(statement, BlockStmt):
            self.emit_block(statement, context)
            return
        if isinstance(statement, VarDeclStmt):
            if statement.initializer is None:
                self.emit("  lda #0x00")
            else:
                self.emit_expression(statement.initializer, context)
            self.emit(f"  sta {self.resolve_variable(statement.name, context)}")
            return
        if isinstance(statement, AssignStmt):
            self.emit_assignment(statement.target, statement.value, context)
            return
        if isinstance(statement, ExprStmt):
            self.emit_expression(statement.expr, context)
            return
        if isinstance(statement, ReturnStmt):
            if statement.value is None:
                if context.return_type != "void":
                    self.emit("  lda #0x00")
            else:
                self.emit_expression(statement.value, context)
            self.emit("  rts")
            return
        if isinstance(statement, IfStmt):
            else_label = self.new_label(f"{context.name}_else")
            end_label = self.new_label(f"{context.name}_endif")
            self.emit_condition_branch_false(statement.condition, else_label, context)
            self.emit_block(statement.then_block, context)
            if statement.else_block is None:
                self.emit(f"{else_label}:")
                return
            self.emit(f"  jmp {end_label}")
            self.emit(f"{else_label}:")
            self.emit_block(statement.else_block, context)
            self.emit(f"{end_label}:")
            return
        if isinstance(statement, WhileStmt):
            start_label = self.new_label(f"{context.name}_while")
            end_label = self.new_label(f"{context.name}_wend")
            self.emit(f"{start_label}:")
            self.emit_condition_branch_false(statement.condition, end_label, context)
            self.emit_block(statement.body, context)
            self.emit(f"  jmp {start_label}")
            self.emit(f"{end_label}:")
            return
        raise CompileError(f"unsupported statement node {statement!r}")

    def emit_condition_branch_false(self, expr: Expr, false_label: str, context: FunctionContext) -> None:
        continue_label = self.new_label(f"{context.name}_cond_continue")
        self.emit_expression(expr, context)
        self.emit("  cmp #0x00")
        self.emit(f"  bne {continue_label}")
        self.emit(f"  jmp {false_label}")
        self.emit(f"{continue_label}:")

    def emit_assignment(self, target: object, value: Expr, context: FunctionContext) -> None:
        if isinstance(target, VarLValue):
            self.emit_expression(value, context)
            self.emit(f"  sta {self.resolve_variable(target.name, context)}")
            return
        if isinstance(target, ArrayLValue):
            declaration = self.globals.get(target.name)
            if declaration is None or declaration.array_size is None:
                raise CompileError(f"unknown array {target.name!r}")
            with self.temp() as index_slot:
                with self.temp() as value_slot:
                    self.emit_expression(target.index, context)
                    self.emit(f"  sta {index_slot}")
                    self.emit_expression(value, context, allow_calls=False)
                    self.emit(f"  sta {value_slot}")
                    self.emit(f"  ldx {index_slot}")
                    self.emit(f"  lda {value_slot}")
                    self.emit(f"  sta {self.resolve_array_base(declaration)}, x")
            return
        raise CompileError(f"unsupported assignment target {target!r}")

    def emit_expression(self, expr: Expr, context: FunctionContext, allow_calls: bool = True) -> None:
        if isinstance(expr, NumberExpr):
            self.emit(f"  lda #{self.byte_literal(expr.value)}")
            return
        if isinstance(expr, VarExpr):
            self.emit(f"  lda {self.resolve_variable(expr.name, context)}")
            return
        if isinstance(expr, ArrayAccessExpr):
            declaration = self.globals.get(expr.name)
            if declaration is None or declaration.array_size is None:
                raise CompileError(f"unknown array {expr.name!r}")
            with self.temp() as index_slot:
                self.emit_expression(expr.index, context, allow_calls=allow_calls)
                self.emit(f"  sta {index_slot}")
                self.emit(f"  ldx {index_slot}")
                self.emit(f"  lda {self.resolve_array_base(declaration)}, x")
            return
        if isinstance(expr, CallExpr):
            self.emit_call(expr, context, allow_calls=allow_calls)
            return
        if isinstance(expr, UnaryExpr):
            if expr.op == "!":
                true_label = self.new_label(f"{context.name}_not_true")
                done_label = self.new_label(f"{context.name}_not_done")
                self.emit_expression(expr.operand, context, allow_calls=allow_calls)
                self.emit("  cmp #0x00")
                self.emit(f"  beq {true_label}")
                self.emit("  lda #0x00")
                self.emit(f"  jmp {done_label}")
                self.emit(f"{true_label}:")
                self.emit("  lda #0x01")
                self.emit(f"{done_label}:")
                return
            if expr.op == "-":
                with self.temp() as slot:
                    self.emit_expression(expr.operand, context, allow_calls=allow_calls)
                    self.emit(f"  sta {slot}")
                    self.emit("  lda #0x00")
                    self.emit("  sec")
                    self.emit(f"  sbc {slot}")
                return
            raise CompileError(f"unsupported unary operator {expr.op!r}")
        if isinstance(expr, BinaryExpr):
            self.emit_binary(expr, context, allow_calls=allow_calls)
            return
        raise CompileError(f"unsupported expression node {expr!r}")

    def emit_binary(self, expr: BinaryExpr, context: FunctionContext, allow_calls: bool) -> None:
        if expr.op in {"+", "&", "|", "^"}:
            with self.temp() as slot:
                self.emit_expression(expr.left, context, allow_calls=allow_calls)
                self.emit(f"  sta {slot}")
                self.emit_expression(expr.right, context, allow_calls=False)
                if expr.op == "+":
                    self.emit("  clc")
                    self.emit(f"  adc {slot}")
                elif expr.op == "&":
                    self.emit(f"  and {slot}")
                elif expr.op == "|":
                    self.emit(f"  ora {slot}")
                else:
                    self.emit(f"  eor {slot}")
            return

        if expr.op == "-":
            with self.temp() as left_slot:
                with self.temp() as right_slot:
                    self.emit_expression(expr.left, context, allow_calls=allow_calls)
                    self.emit(f"  sta {left_slot}")
                    self.emit_expression(expr.right, context, allow_calls=False)
                    self.emit(f"  sta {right_slot}")
                    self.emit(f"  lda {left_slot}")
                    self.emit("  sec")
                    self.emit(f"  sbc {right_slot}")
            return

        if expr.op in {"==", "!=", "<", "<=", ">", ">="}:
            true_label = self.new_label(f"{context.name}_cmp_true")
            done_label = self.new_label(f"{context.name}_cmp_done")
            with self.temp() as left_slot:
                with self.temp() as right_slot:
                    self.emit_expression(expr.left, context, allow_calls=allow_calls)
                    self.emit(f"  sta {left_slot}")
                    self.emit_expression(expr.right, context, allow_calls=False)
                    self.emit(f"  sta {right_slot}")
                    self.emit(f"  lda {left_slot}")
                    self.emit(f"  cmp {right_slot}")
                    if expr.op == "==":
                        self.emit(f"  beq {true_label}")
                    elif expr.op == "!=":
                        self.emit(f"  bne {true_label}")
                    elif expr.op == "<":
                        self.emit(f"  bcc {true_label}")
                    elif expr.op == "<=":
                        self.emit(f"  bcc {true_label}")
                        self.emit(f"  beq {true_label}")
                    elif expr.op == ">":
                        skip_label = self.new_label(f"{context.name}_cmp_skip")
                        self.emit(f"  beq {skip_label}")
                        self.emit(f"  bcs {true_label}")
                        self.emit(f"{skip_label}:")
                    else:
                        self.emit(f"  bcs {true_label}")
                    self.emit("  lda #0x00")
                    self.emit(f"  jmp {done_label}")
                    self.emit(f"{true_label}:")
                    self.emit("  lda #0x01")
                    self.emit(f"{done_label}:")
            return

        raise CompileError(f"unsupported binary operator {expr.op!r}")

    def emit_call(self, expr: CallExpr, context: FunctionContext, allow_calls: bool) -> None:
        if not allow_calls:
            raise CompileError("function calls are only supported when no temporaries are live")
        function = self.functions.get(expr.name)
        if function is None:
            raise CompileError(f"call to unknown function {expr.name!r}")
        if len(expr.args) != len(function.parameters):
            raise CompileError(
                f"function {expr.name!r} expects {len(function.parameters)} arguments "
                f"but got {len(expr.args)}"
            )

        with self.reserve_temps(len(expr.args)) as arg_slots:
            for slot, argument in zip(arg_slots, expr.args):
                self.emit_expression(argument, context)
                self.emit(f"  sta {slot}")
            for slot, parameter in zip(arg_slots, function.parameters):
                self.emit(f"  lda {slot}")
                self.emit(f"  sta {self.function_params[function.name][parameter.name]}")
        self.emit(f"  jsr {function.name}")

    def resolve_variable(self, name: str, context: FunctionContext) -> str:
        if name in context.storage_labels:
            return context.storage_labels[name]
        declaration = self.globals.get(name)
        if declaration is None:
            raise CompileError(f"unknown variable {name!r}")
        if declaration.array_size is not None:
            raise CompileError(f"array {name!r} cannot be used as a scalar value")
        if declaration.absolute_address is not None:
            return self.word_literal(declaration.absolute_address)
        return declaration.name

    def resolve_global_storage(self, declaration: GlobalDecl) -> str:
        if declaration.array_size is not None:
            raise CompileError(f"array {declaration.name!r} does not have scalar storage")
        if declaration.absolute_address is not None:
            return self.word_literal(declaration.absolute_address)
        return declaration.name

    def resolve_array_base(self, declaration: GlobalDecl) -> str:
        if declaration.array_size is None:
            raise CompileError(f"{declaration.name!r} is not an array")
        if declaration.absolute_address is not None:
            return self.word_literal(declaration.absolute_address)
        return declaration.name

    def emit_global_initializer(self, declaration: GlobalDecl) -> None:
        if declaration.array_size is None:
            if declaration.absolute_address is not None and declaration.initializer is None:
                continue_init = False
            else:
                continue_init = True
            if not continue_init:
                return
            init_value = 0 if declaration.initializer is None else self.eval_const_expr(declaration.initializer)
            self.emit(f"  lda #{self.byte_literal(init_value)}")
            self.emit(f"  sta {self.resolve_global_storage(declaration)}")
            return

        values: tuple[int, ...] = ()
        if isinstance(declaration.initializer, ArrayInitializer):
            values = tuple(self.eval_const_expr(expr) for expr in declaration.initializer.values)
        for index in range(declaration.array_size):
            value = values[index] if index < len(values) else 0
            self.emit(f"  lda #{self.byte_literal(value)}")
            self.emit(f"  sta {self.resolve_array_element_literal(declaration, index)}")

    def resolve_array_element_literal(self, declaration: GlobalDecl, index: int) -> str:
        if declaration.array_size is None:
            raise CompileError(f"{declaration.name!r} is not an array")
        if declaration.absolute_address is not None:
            return self.word_literal(declaration.absolute_address + index)
        if index == 0:
            return declaration.name
        return f"{declaration.name}+{index}"

    def eval_const_expr(self, expr: Expr) -> int:
        if isinstance(expr, NumberExpr):
            return expr.value & 0xFF
        if isinstance(expr, UnaryExpr):
            value = self.eval_const_expr(expr.operand)
            if expr.op == "-":
                return (-value) & 0xFF
            if expr.op == "!":
                return 0x01 if value == 0 else 0x00
        if isinstance(expr, BinaryExpr):
            left = self.eval_const_expr(expr.left)
            right = self.eval_const_expr(expr.right)
            if expr.op == "+":
                return (left + right) & 0xFF
            if expr.op == "-":
                return (left - right) & 0xFF
            if expr.op == "&":
                return left & right
            if expr.op == "|":
                return left | right
            if expr.op == "^":
                return left ^ right
            if expr.op == "==":
                return 0x01 if left == right else 0x00
            if expr.op == "!=":
                return 0x01 if left != right else 0x00
            if expr.op == "<":
                return 0x01 if left < right else 0x00
            if expr.op == "<=":
                return 0x01 if left <= right else 0x00
            if expr.op == ">":
                return 0x01 if left > right else 0x00
            if expr.op == ">=":
                return 0x01 if left >= right else 0x00
        raise CompileError("global initializers must be constant u8 expressions")

    @contextmanager
    def reserve_temps(self, count: int):
        if count == 0:
            yield []
            return
        if self.temp_depth + count > TEMP_COUNT:
            raise CompileError("function call arguments exhausted temporary storage")
        start = self.temp_depth
        self.temp_depth += count
        try:
            yield [f"__tmp{start + index}" for index in range(count)]
        finally:
            self.temp_depth -= count

    @contextmanager
    def temp(self):
        if self.temp_depth >= TEMP_COUNT:
            raise CompileError("expression nesting exhausted temporary storage")
        name = f"__tmp{self.temp_depth}"
        self.temp_depth += 1
        try:
            yield name
        finally:
            self.temp_depth -= 1

    def new_label(self, prefix: str) -> str:
        value = f"__{prefix}_{self.label_counter}"
        self.label_counter += 1
        return value

    def emit(self, line: str) -> None:
        self.lines.append(line)

    def byte_literal(self, value: int) -> str:
        return f"0x{value & 0xFF:02x}"

    def word_literal(self, value: int) -> str:
        return f"0x{value & 0xFFFF:04x}"
