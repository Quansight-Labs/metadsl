import ast
import functools
import inspect
import typing

import astunparse
import numpy

from .core import *
from .dispatch import *
from .numpy import *


# indices will have length now for arrays
__all__ = ["jit"]
T_call = typing.TypeVar("T_call", bound=typing.Callable)


def jit(*dims: int) -> typing.Callable[[T_call], T_call]:
    def inner(fn: T_call) -> T_call:
        arg_names = list(inspect.signature(fn).parameters.keys())
        nargs = len(arg_names)

        def wrapper_fn(*args):
            return fn(
                *(
                    LazyNDArray.create(to_array(arg)).with_dim(Natural(dim))
                    for (arg, dim) in zip(args, dims)
                )
            ).array

        orig_res = Abstraction.create_nary(
            wrapper_fn, arg_names, *([Array(None, Box())] * nargs)
        )
        res = replace(orig_res)
        # return res
        new_res = res
        for arg_name in arg_names:
            new_res = new_res(Box(AST(ast.Name(arg_name, ast.Load()))))

        # return new_res
        # return create_and_fill(replace(new_res))
        new_res_ = replace(create_and_fill(new_res))  # type: ignore
        # return new_res
        # return new_res
        replaced = replace(to_ast(new_res_))
        # return replaced
        res_ast = replaced.value
        if not isinstance(res_ast, AST):
            from IPython.display import display

            display(replaced)
            raise NotImplementedError("Couldn't compile to AST")
        args_ = ast.arguments(
            args=[ast.arg(arg=a, annotation=None) for a in arg_names],
            vararg=None,
            kwonlyargs=[],
            kw_defaults=[],
            kwarg=None,
            defaults=[],
        )
        fn_ast = ast.Module(
            body=[
                ast.FunctionDef(
                    name="fn",
                    args=args_,
                    body=[*res_ast.init, ast.Return(value=res_ast.get)],
                    decorator_list=[],
                    returns=None,
                )
            ]
        )
        source = astunparse.unparse(fn_ast)
        locals_: typing.Dict[str, typing.Any] = {}
        exec(
            compile(  # type: ignore
                ast.fix_missing_locations(fn_ast), filename="<ast>", mode="exec"
            ),
            {"numpy": numpy},
            locals_,
        )
        wrapped_fn = functools.wraps(fn)(locals_["fn"])
        wrapped_fn.source = source  # type: ignore
        wrapped_fn.res = res  # type: ignore
        wrapped_fn.new_res = new_res  # type: ignore
        wrapped_fn.orig_res = orig_res  # type: ignore
        return typing.cast(T_call, wrapped_fn)

    return inner
