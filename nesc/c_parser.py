from __future__ import annotations

from dataclasses import dataclass


KEYWORDS = {"u8", "void", "volatile", "if", "else", "while", "return"}


class ParseError(ValueError):
    pass


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    line: int
    column: int


@dataclass(frozen=True)
class Program:
    globals: tuple["GlobalDecl", ...]
    functions: tuple["FunctionDecl", ...]


@dataclass(frozen=True)
class GlobalDecl:
    name: str
    type_name: str
    is_volatile: bool
    array_size: int | None
    absolute_address: int | None
    initializer: "Initializer | None"


@dataclass(frozen=True)
class FunctionDecl:
    name: str
    return_type: str
    parameters: tuple["ParamDecl", ...]
    body: "BlockStmt"


@dataclass(frozen=True)
class BlockStmt:
    statements: tuple["Stmt", ...]


class Stmt:
    pass


class Expr:
    pass


@dataclass(frozen=True)
class ParamDecl:
    name: str
    type_name: str


@dataclass(frozen=True)
class VarDeclStmt(Stmt):
    name: str
    initializer: Expr | None


class LValue:
    pass


@dataclass(frozen=True)
class VarLValue(LValue):
    name: str


@dataclass(frozen=True)
class ArrayLValue(LValue):
    name: str
    index: Expr


@dataclass(frozen=True)
class AssignStmt(Stmt):
    target: LValue
    value: Expr


@dataclass(frozen=True)
class IfStmt(Stmt):
    condition: Expr
    then_block: BlockStmt
    else_block: BlockStmt | None


@dataclass(frozen=True)
class WhileStmt(Stmt):
    condition: Expr
    body: BlockStmt


@dataclass(frozen=True)
class ReturnStmt(Stmt):
    value: Expr | None


@dataclass(frozen=True)
class ExprStmt(Stmt):
    expr: Expr


@dataclass(frozen=True)
class NumberExpr(Expr):
    value: int


@dataclass(frozen=True)
class VarExpr(Expr):
    name: str


@dataclass(frozen=True)
class ArrayAccessExpr(Expr):
    name: str
    index: Expr


@dataclass(frozen=True)
class UnaryExpr(Expr):
    op: str
    operand: Expr


@dataclass(frozen=True)
class BinaryExpr(Expr):
    op: str
    left: Expr
    right: Expr


@dataclass(frozen=True)
class CallExpr(Expr):
    name: str
    args: tuple[Expr, ...]


@dataclass(frozen=True)
class ArrayInitializer:
    values: tuple[Expr, ...]


Initializer = Expr | ArrayInitializer


def parse_program(source: str) -> Program:
    return Parser(tokenize(source)).parse_program()


def tokenize(source: str) -> list[Token]:
    tokens: list[Token] = []
    index = 0
    line = 1
    column = 1

    def current() -> str:
        return source[index] if index < len(source) else "\0"

    while index < len(source):
        char = current()
        if char in " \t\r":
            index += 1
            column += 1
            continue
        if char == "\n":
            index += 1
            line += 1
            column = 1
            continue
        if source.startswith("//", index):
            while index < len(source) and source[index] != "\n":
                index += 1
                column += 1
            continue
        if source.startswith("/*", index):
            end = source.find("*/", index + 2)
            if end == -1:
                raise ParseError(f"unterminated block comment at {line}:{column}")
            comment = source[index : end + 2]
            line += comment.count("\n")
            if "\n" in comment:
                column = len(comment.rsplit("\n", 1)[-1]) + 1
            else:
                column += len(comment)
            index = end + 2
            continue
        if char.isalpha() or char == "_":
            start = index
            start_col = column
            while index < len(source) and (source[index].isalnum() or source[index] == "_"):
                index += 1
                column += 1
            value = source[start:index]
            kind = value if value in KEYWORDS else "IDENT"
            tokens.append(Token(kind=kind, value=value, line=line, column=start_col))
            continue
        if char.isdigit():
            start = index
            start_col = column
            if source.startswith(("0x", "0X"), index):
                index += 2
                column += 2
                while index < len(source) and source[index] in "0123456789abcdefABCDEF":
                    index += 1
                    column += 1
            else:
                while index < len(source) and source[index].isdigit():
                    index += 1
                    column += 1
            tokens.append(Token(kind="NUMBER", value=source[start:index], line=line, column=start_col))
            continue

        two_char = source[index : index + 2]
        if two_char in {"==", "!=", "<=", ">="}:
            tokens.append(Token(kind=two_char, value=two_char, line=line, column=column))
            index += 2
            column += 2
            continue

        if char in "{}[]();,@+-&|^!<>=":
            tokens.append(Token(kind=char, value=char, line=line, column=column))
            index += 1
            column += 1
            continue

        raise ParseError(f"unexpected character {char!r} at {line}:{column}")

    tokens.append(Token(kind="EOF", value="", line=line, column=column))
    return tokens


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.index = 0

    def parse_program(self) -> Program:
        globals_: list[GlobalDecl] = []
        functions: list[FunctionDecl] = []
        while not self.check("EOF"):
            declaration = self.parse_top_level()
            if isinstance(declaration, GlobalDecl):
                globals_.append(declaration)
            else:
                functions.append(declaration)
        return Program(globals=tuple(globals_), functions=tuple(functions))

    def parse_top_level(self) -> GlobalDecl | FunctionDecl:
        is_volatile = self.match("volatile")
        type_token = self.expect_any({"u8", "void"})
        name = self.expect("IDENT").value

        if self.match("("):
            parameters = self.parse_parameter_list()
            body = self.parse_block()
            return FunctionDecl(name=name, return_type=type_token.kind, parameters=parameters, body=body)

        if type_token.kind == "void":
            raise self.error(type_token, "void is only valid for function declarations")

        array_size = None
        if self.match("["):
            array_size = self.parse_number_token(self.expect("NUMBER"))
            self.expect("]")

        absolute_address = None
        initializer: Initializer | None = None
        if self.match("@"):
            absolute_address = self.parse_number_token(self.expect("NUMBER"))
        if self.match("="):
            initializer = self.parse_initializer()
        self.expect(";")
        return GlobalDecl(
            name=name,
            type_name=type_token.kind,
            is_volatile=is_volatile,
            array_size=array_size,
            absolute_address=absolute_address,
            initializer=initializer,
        )

    def parse_initializer(self) -> Initializer:
        if self.match("{"):
            values: list[Expr] = []
            if not self.check("}"):
                while True:
                    values.append(self.parse_expression())
                    if not self.match(","):
                        break
            self.expect("}")
            return ArrayInitializer(values=tuple(values))
        return self.parse_expression()

    def parse_parameter_list(self) -> tuple[ParamDecl, ...]:
        if self.match("void"):
            self.expect(")")
            return ()
        if self.check(")"):
            self.expect(")")
            return ()

        parameters: list[ParamDecl] = []
        while True:
            type_token = self.expect("u8")
            name = self.expect("IDENT").value
            parameters.append(ParamDecl(name=name, type_name=type_token.kind))
            if not self.match(","):
                break
        self.expect(")")
        return tuple(parameters)

    def parse_block(self) -> BlockStmt:
        self.expect("{")
        statements: list[Stmt] = []
        while not self.check("}"):
            statements.append(self.parse_statement())
        self.expect("}")
        return BlockStmt(statements=tuple(statements))

    def parse_statement(self) -> Stmt:
        if self.check("{"):
            return self.parse_block()
        if self.match("u8"):
            name = self.expect("IDENT").value
            initializer = self.parse_expression() if self.match("=") else None
            self.expect(";")
            return VarDeclStmt(name=name, initializer=initializer)
        if self.match("if"):
            self.expect("(")
            condition = self.parse_expression()
            self.expect(")")
            then_block = self.parse_block()
            else_block = self.parse_block() if self.match("else") else None
            return IfStmt(condition=condition, then_block=then_block, else_block=else_block)
        if self.match("while"):
            self.expect("(")
            condition = self.parse_expression()
            self.expect(")")
            return WhileStmt(condition=condition, body=self.parse_block())
        if self.match("return"):
            if self.check(";"):
                self.expect(";")
                return ReturnStmt(value=None)
            value = self.parse_expression()
            self.expect(";")
            return ReturnStmt(value=value)
        if self.is_assignment_start():
            target = self.parse_lvalue()
            self.expect("=")
            value = self.parse_expression()
            self.expect(";")
            return AssignStmt(target=target, value=value)

        expr = self.parse_expression()
        self.expect(";")
        return ExprStmt(expr=expr)

    def is_assignment_start(self) -> bool:
        if not self.check("IDENT"):
            return False
        if self.peek_next().kind == "=":
            return True
        if self.peek_next().kind != "[":
            return False
        depth = 0
        index = self.index + 1
        while index < len(self.tokens):
            kind = self.tokens[index].kind
            if kind == "[":
                depth += 1
            elif kind == "]":
                depth -= 1
                if depth == 0:
                    return self.tokens[index + 1].kind == "="
            index += 1
        return False

    def parse_lvalue(self) -> LValue:
        name = self.expect("IDENT").value
        if self.match("["):
            index = self.parse_expression()
            self.expect("]")
            return ArrayLValue(name=name, index=index)
        return VarLValue(name=name)

    def parse_expression(self) -> Expr:
        return self.parse_bitwise_or()

    def parse_bitwise_or(self) -> Expr:
        expr = self.parse_bitwise_xor()
        while self.match("|"):
            expr = BinaryExpr(op="|", left=expr, right=self.parse_bitwise_xor())
        return expr

    def parse_bitwise_xor(self) -> Expr:
        expr = self.parse_bitwise_and()
        while self.match("^"):
            expr = BinaryExpr(op="^", left=expr, right=self.parse_bitwise_and())
        return expr

    def parse_bitwise_and(self) -> Expr:
        expr = self.parse_equality()
        while self.match("&"):
            expr = BinaryExpr(op="&", left=expr, right=self.parse_equality())
        return expr

    def parse_equality(self) -> Expr:
        expr = self.parse_comparison()
        while True:
            if self.match("=="):
                expr = BinaryExpr(op="==", left=expr, right=self.parse_comparison())
            elif self.match("!="):
                expr = BinaryExpr(op="!=", left=expr, right=self.parse_comparison())
            else:
                return expr

    def parse_comparison(self) -> Expr:
        expr = self.parse_additive()
        while True:
            if self.match("<"):
                expr = BinaryExpr(op="<", left=expr, right=self.parse_additive())
            elif self.match("<="):
                expr = BinaryExpr(op="<=", left=expr, right=self.parse_additive())
            elif self.match(">"):
                expr = BinaryExpr(op=">", left=expr, right=self.parse_additive())
            elif self.match(">="):
                expr = BinaryExpr(op=">=", left=expr, right=self.parse_additive())
            else:
                return expr

    def parse_additive(self) -> Expr:
        expr = self.parse_unary()
        while True:
            if self.match("+"):
                expr = BinaryExpr(op="+", left=expr, right=self.parse_unary())
            elif self.match("-"):
                expr = BinaryExpr(op="-", left=expr, right=self.parse_unary())
            else:
                return expr

    def parse_unary(self) -> Expr:
        if self.match("!"):
            return UnaryExpr(op="!", operand=self.parse_unary())
        if self.match("-"):
            return UnaryExpr(op="-", operand=self.parse_unary())
        return self.parse_primary()

    def parse_primary(self) -> Expr:
        if self.match("("):
            expr = self.parse_expression()
            self.expect(")")
            return expr
        if self.check("NUMBER"):
            return NumberExpr(value=self.parse_number_token(self.advance()))
        if self.check("IDENT"):
            name = self.advance().value
            if self.match("("):
                return CallExpr(name=name, args=self.parse_argument_list())
            if self.match("["):
                index = self.parse_expression()
                self.expect("]")
                return ArrayAccessExpr(name=name, index=index)
            return VarExpr(name=name)
        raise self.error(self.peek(), "expected an expression")

    def parse_argument_list(self) -> tuple[Expr, ...]:
        if self.check(")"):
            self.expect(")")
            return ()

        args: list[Expr] = []
        while True:
            args.append(self.parse_expression())
            if not self.match(","):
                break
        self.expect(")")
        return tuple(args)

    def parse_number_token(self, token: Token) -> int:
        if token.value.lower().startswith("0x"):
            return int(token.value, 16)
        return int(token.value, 10)

    def match(self, kind: str) -> bool:
        if self.check(kind):
            self.index += 1
            return True
        return False

    def expect(self, kind: str) -> Token:
        token = self.peek()
        if token.kind != kind:
            raise self.error(token, f"expected {kind!r}")
        self.index += 1
        return token

    def expect_any(self, kinds: set[str]) -> Token:
        token = self.peek()
        if token.kind not in kinds:
            names = ", ".join(sorted(kinds))
            raise self.error(token, f"expected one of: {names}")
        self.index += 1
        return token

    def check(self, kind: str) -> bool:
        return self.peek().kind == kind

    def advance(self) -> Token:
        token = self.peek()
        self.index += 1
        return token

    def peek(self) -> Token:
        return self.tokens[self.index]

    def peek_next(self) -> Token:
        return self.tokens[self.index + 1]

    def error(self, token: Token, message: str) -> ParseError:
        return ParseError(f"{message} at {token.line}:{token.column}")
