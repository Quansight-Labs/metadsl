# uarray - Universal Array Interface

[![Join the chat at https://gitter.im/Plures/uarray](https://badges.gitter.im/Plures/uarray.svg)](https://gitter.im/Plures/uarray?utm_source=badge&utm_medium=badge&utm_campaign=pr-badge&utm_content=badge) [![Binder](https://mybinder.org/badge.svg)](https://mybinder.org/v2/gh/Quansight-Labs/uarray/master?urlpath=lab/tree/notebooks/NumPy%20Compat.ipynb) [![Build Status](https://dev.azure.com/teoliphant/teoliphant/_apis/build/status/Quansight-Labs.uarray)](https://dev.azure.com/teoliphant/teoliphant/_build/latest?definitionId=1) [![PyPI](https://img.shields.io/pypi/v/uarray.svg?style=flat-square)](https://pypi.org/project/uarray/)


- [Road Map](https://github.com/Quansight-Labs/uarray/projects/2)
- [Future Meetings](https://calendar.google.com/calendar/embed?src=quansight.com_cg7sf4usbcn18gdhdb3l2c6v1g%40group.calendar.google.com&ctz=America%2FNew_York)
- [Meeting Notes](https://github.com/Quansight-Labs/uarray/wiki/Meeting-Notes)
- [References](https://github.com/Quansight-Labs/uarray/wiki/References)



## Background

NumPy has become very popular as an array object --- but it implements
a very specific "kind" of array which is sometimes called a fancy
pointer to strided memory. This model is quite popular and has allowed
SciPy and many other tools to be built by linking to existing code.

Over the past decade, newer hardware including GPUs and FPGA, newer
software systems (including JIT compilers and code-generation systems)
have become popular. Also new "kinds" of arrays have been created or
contemplated including distributed arrays, sparse arrays, "unevaluated
arrays", "compressed-storage" arrays, and so forth. Quite often, the
downstream packages and algorithms that use these arrays don't need
the implementation details of the array. They just need a set of basic
operations to work (the interface).

The goal of _uarray_ is to constract an interface to a general array
concept and build a high-level multiple-dispatch mechanism to
re-direct function calls whose implementations are dependent on the
specific kind of array. The desire is for down-stream libraries to be
able to use/expect `uarray` objects based on the interface and then have
their implementation configurable. On-going discussions are happening
on the NumPy mailing list in order to retro-fit NumPy as this array
interface. _uarray_ is an alternative approach with different
contraints and benefits.

Python array computing needs multiple-dispatch. Ufuncs are
fundamentally multiple-dispatch systems, but only at the lowest level.
It is time to raise the visibility of this into Python. This effort
differs from [XND](https://xnd.io/) in that XND is low-level and
cross-langauge. The _uarray_ is "high-level" and Python only. The
concepts could be applied to other languages but we do not try to
solve that problem with this library. XND can be _used_ by some
implementations of the uarray concept.

Our desire with _uarray_ is to build a useful array interface for Python
that can help library writers write to a standard interface while
allowing backend implementers to innovate in performance. This effort
is being incubated at Quansight Labs which is an R&D group inside of
Quansight that hires developers, community/product managers, and
tech-writers to build and maintain shared open-source infrastructure.
It is funded by donations and grants. The efforts are highly
experimental at this stage and we are looking for funding for the
effort in order to make better progress.


## Status
This project is in active development and not ready for production use. However, you can install it with:

```bash
pip install uarray
```


## Development

```bash
conda create -n uarray python=3.7
conda activate uarray
pip install -r requirements.dev.txt
flit install --symlink
```

### Testing

```bash
mypy uarray
python extract_readme_tests.py
py.test
```

To re-run notebooks (their outputs are checked in the tests):

```bash
jupyter nbconvert --to notebook --inplace --execute notebooks/NumPy\ Compat.ipynb notebooks/Transpose\ Test.ipynb notebooks/NumPy\ Broadcasting.ipynb
```

## Internals

Unlike other libraries I have worked on in Python, much of the design of uarray has been focused on the
internal representations instead of the user facing interfaces. From a users perspective, most of these details
are hidden. If you use the `optimize` decorator or even the lower level `LazyNDArray` wrapper, you get back some Python function
you can call that should do what you want and should be fast or efficient in some way. But that isn't actually the interesting or powerful
part of the system. Instead, it's meant to give a framework where users can easily add to the core working internals and the actually
"core" of the system is very minimal. Why this approach? To allow faster iteration as things evolve, without having to rewrite everthing.
I.e. to be able to support a wide array of paradigms of input and output.

So in this section, I want to give an overview of internals of uarray in an attempt to make it extendable by others. I will try to **bold**
any tips that can help avoid subtle errors. Eventually, it would be nice if some these tips were all verified as you develop automatically.

### MatchPy: `uarray/machinery.py`

Fundamentally, uarray is just a set of patterns on top of the [MatchPy](https://github.com/HPAC/matchpy) pattern matching system in Python.

We start with the `matchpy.Expression` class. Most of uarray is subclasses of either `matchpy.Symbol` or `matchpy.Operation`, both of which
are subclasses of `matchpy.Expression`. Every `Symbol` subclasses contain a `name` which is a Python object. They are the leaves of the expression tree.
Whereas each `Operation` subclass is initialized with a number of other `Expressions`s. These are stored on the `operands` attribute of the instance.

TODO: Make `uarray.Int` use just `name`

Here is an example of creating a recursive list in matchpy:

```python
import matchpy

class Int(matchpy.Symbol):
    pass

class Nil(matchpy.Operation):
    name = "Nil"
    arity = matchpy.Arity(0, True)

class Cons(matchpy.Operation):
    """
    Cons(value, list)
    """
    name = "Cons"
    arity = matchpy.Arity(2, True)

class List(matchpy.Operation):
    """
    List(*values)
    """
    name = "List"
    arity = matchpy.Arity(0, False)

nil_list = Nil()
assert not nil_list.operands

v = Int(1)
assert v.name == 1

a = Cons(v, Nil())
assert a.operands == [v, Nil()]

b = List(v)
assert b.operands == [v]
```

Then in uarray we define one global `matchpy.ManyToOneReplacer` that holds a bunch of replacement rules, to take some expression tree and replace it with another.
We define a helper `register` function that takes in an expression to match, some custom contraints, and the replacement function.

We also define two objects, `w` and `ws` that return [`matchpy.Wildcard`](https://matchpy.readthedocs.io/en/latest/api/matchpy.expressions.expressions.html#matchpy.expressions.expressions.Wildcard)s.
If you get an attribute from them, it returns a wildcard with that name. This is a way to extract out some part of the matched pattern and pass it into
the function so that you can use it to return a new pattern. The difference between the two is that `w` creates wildcard that match one and only
one expression, while `ws` matches wildcards that return 0 or more expression. They are like `.` and `.*` in regex land.

Let's show how this works in this example, by adding a rule to turn Lists expression into nested Cons expressions:

```python
import uarray

# base case
uarray.register(List(), lambda: Nil())
uarray.register(List(uarray.w("x"), uarray.ws("xs")), lambda x, xs: Cons(x, List(*xs)))
```

To use the global replacer on an expression, we provide the `replace` function. It takes in some expression and keep applying replacement rules
that match (in arbitrary order) until it cannot find any more to replace.

Two things to note about this. If two replacement rules could match the same expression, then which one is executed is not fixed. Therefore,
there **should not be multiple replacement rules registered that could match the same pattern**. If there are, you might get non deterministic compilation.
The other thing is that replacement rules are fundementally one way. They are not equivalencies. So it becomes helpful to think about
**what are the types of expressions I have when I start and what are the types of expression I have when everything has been replaced**.
In this case, we start with higher level `List` forms and end up with lower level nested `Cons` forms.

Let's see this in action:

```python
assert uarray.replace(List()) == Nil()
assert uarray.replace(b) == a
```

Since each replacement happens in a sequence, it is often helpful to look at not just the final replaced form, but all the intermediate forms as well.
For that, we provide the `replace_scan`, which returns an iterable of all the replacements. This can also be helpful to use to debug infintely replacing forms,
because it is lazily evaluted.

```python
assert list(uarray.replace_scan(List())) == [List(), Nil()]
assert list(uarray.replace_scan(b)) == [List(v), Cons(v, List()), Cons(v, Nil())]
```

One interesting thing to note here is that as the expression moves from what the user enters (`List(x, ...)`)
to the final form (`Cons(a, Cons(...))`) we move through intermediate forms that have both types of expressions.
So it's also helpful to not only think about what kinds of forms should we start with and what kinds should we end with,
but **making sure that the expression still has a meaningful form as it progresses**. This helps reasonsing about
intermediate forms to make sure they are "correct" in the sense that they express what you want them to. Otherwise, it
can be hard to diagnose where things go wrong and reason about the state.

There is one last note about our use of Matchpy. When you construct any form in MatchPy, you can also provide a `variable_name` for it.
Then you can use the `matchpy.substitute` function to replace any values with that `variable_name` with another expression. For example:

```python
v_p = Int(None, variable_name="A")
assert matchpy.substitute(Cons(v_p, Nil()), {"A": Int(1)}) == Cons(Int(1), Nil())
```

### Arrays (and contents and callables): `uarray/core.py`

TODO: Look at other names for contents and callables. Content could become Int, if we change Int
as it is to just be typed versions of itself. aka have Integer and String but not base Int symbol.

There are many ways we could implement the concept of a multi dimensional array in MatchPy.
We are interested in ways to do this that will let us express take high level descriptions of array operations,
like those present in Lenore Mullin's these, A Mathematics of Arrays (MoA), and replace them with simpler expressions.
That work treats arrays as having two things, a shape and a function to go from an index to a value.

Here we think about arrays as a `Sequence(length, getitem)`, a `Scalar(content)`, or any form that can be replaced into these forms.
Let's start with an example, using these expressions, then we can get into the weeds of what this all means.

```python
s = uarray.Scalar(uarray.Int(10))

assert uarray.replace(uarray.Content(s)) == uarray.Int(10)
```

We see that a `Scalar` just wraps some underlying thing, we call the contents. We can extract
out it out with the `Content` operator. Now let's look at a `Sequence`:

```python
class Always(matchpy.Operation):
    name = "Always"
    arity = matchpy.Arity(1, True)

a = uarray.Sequence(
    uarray.Int(5),
    Always(s)
)

assert uarray.replace(uarray.Length(a)) == uarray.Int(5)
assert uarray.replace(uarray.GetItem(a)) == Always(s)
```

Here we define `a` to be a sequence of length 5 that contains all scalars of value 10.
We can also understand this as a one dimensional array, like `np.array([10, 10, 10, 10, 10])`.

We see that a sequence has two items we can extract out, the `GetItem`
and the `Length`. But what is this `Always` operator? Well we just defined it.
The getitem part of the sequence should be a callable that takes in an index of type
contents and returns an array. So let's make `Always` a callable that works like this:

```python
uarray.register(uarray.CallUnary(Always(uarray.w("x")), uarray.w("idx")), lambda x, idx: x)
```

A callable is any expression that you can use `uarray.CallUnary` on it as the first argument,
and it's arguments as the rest of the arguments. It should replace this form into it's result.
In this case, we have a simple `Callable` that takes one argument and just returns what is inside of it.
i.e. it doesn't matter what it is called with, it always returns it's first operand.

Now, we can get the callable from the array and call it on an index:

```python
idx = uarray.Int(2)

indexed_a = uarray.CallUnary(
    uarray.GetItem(a),
    idx
)

assert uarray.replace(indexed_a) == s
```

This is how we index arrays in uarray. We extract out their callables and call them with the index. The `Index` function in Mathematics of Arrays (or in NumPy) allows you to index an array with a vector, just like how in NumPy you can index an array with a tuple of indices.

How does it work? If you look at it's defintion in `uarray/moa.py` you will see it uses this pattern above once for each index in the vector.

A mistake I often make is giving an expression of the wrong type to some expression.
For example, what if I defined an array like this:

```python
uarray.Sequence(uarray.Scalar(uarray.Int(10)), Always(uarray.Scalar(10)))
```

Can you spot what is wrong? The length of the sequence is an Array not a contents!
So this should instead be:

```python
uarray.Sequence(uarray.Int(10), Always(uarray.Scalar(10)))
```

What do I mean "should"? Will this give an error? An exception? Most likely it will not.
You will just end up with some long expression down the line that cannot be reduced
because it has the wrong type inside. It's like casting a pointer to another type in C
and then reading in the values. It won't error when you cast the pointer, but the contents
of it doesn't have the write structure to be meaningful.

The moral is
**always understand what types of expressions your expression takes and don't pass those of another class.**

TODO: Enforce this somehow. We could possibly use python types to define these different
classes and have each expression subclass subclass also from this Python type. This could
get static type checking (possibly). But it comes at the expense of introducing a Python
type hierarchy where we don't really need one, just for MyPy.

#### Callables

You might have a lot of questions about callables at this point. Let's show a few
more examples of built in callables, and then we can get into the nitty gritty of why
they are implemented like they are.

First, let's look at the `Function(body, *arg_names)` callable. This let's you define the body of the function
with the arguments as `Unbound` values with their `variable_name` set. To "execute"/"call"
the `Function` callable, we just replace those values with their arguments:

```python
arg = uarray.unbound("some_unique_value")
squared = uarray.UnaryFunction(uarray.Multiply(arg, arg), arg)
v = uarray.Int(5)
called = uarray.CallUnary(squared, v)

assert uarray.replace(called) == uarray.Int(25)
assert list(uarray.replace_scan(called)) == [
    called,
    uarray.Multiply(v, v),
    uarray.Int(25)
]
```

`Function` takes in the argument names as the rest of the args after the body.
When it is called, each argument is matched to it's name and the `matchpy.substitute` function
(which we talked about in the first section) is used to replace the args with their values in the body. You can see the full replacement rule for how this executes in `uarray/core.py`.

Another example is the `Vector(*items)` which takes in an index "i" and returns the "i"th arg:

TODO: change vector callable to not wrap in scalar

```python
c = uarray.Vector(uarray.Int(5), uarray.Int(10))
assert uarray.replace(uarray.CallUnary(c, uarray.Int(0))) == uarray.Int(5)
assert uarray.replace(uarray.CallUnary(c, uarray.Int(1))) == uarray.Int(10)
```

In the next section, we will also see how callables are used for compiling to
the Python AST.

But why have callables? It started with just having a getitem and needing an
operation to evaluate that getitem with an index to return the sub array. Then
I also needed a way when applying a reduction or broadcasting binary operators
to hold onto the underlying operation and then apply it later on. At first,
these things were all distinct operators. I also was just holding onto
Python language callables, like lambdas or classes, inside of a Symbol
and then executing that when I needed to see the result.

However, if we use Python callable, then we can't "see inside" of the body.
So if we translate this later to some backend, we have to inspect the Python code/class
to see how we translate it. Seems like extra wasted work when we are already have
a way to hold these things in an introspectable and reducable form, as matchpy expressions.
And, if we keep the expressions as MatchPy forms, then they can be reduced, even before they are called.

So why not just have everthing be a `Function` instead of introducing other callables? Well it allows
us to move some of the application logic into Python land instead of keeping it generic. For example,
we _could_ define `Vector` to be a `Function`, but it would require basically a big pattern
matching statement of like "if index == 0, then return this value, elif equal to 1 return this value".

We could implement this all with matchpy operations, but it just requires a lot of extra work, extra forms, and for what gain? Well the gain would be we could then translate this lower level form to a backend without a concept of a Vector, just with a concept of `if, else`.

The other side of this added flexibity is the ability to "overload" any matchpy expression to make it
callable. How? Well you just define a call replacement for it and then it's callable. We will use
this to our advantage in the Python AST creation.

Another option would be to express all functions in a fixed point form, with composition and other operators like that. This might be helpful in the end, to move from `Function` to this type of thing.
See [Compiling to Categories](http://conal.net/papers/compiling-to-categories/) for one explenation
of this type of transformation.

### Mathematics of Arrays: `array/moa.py`

We are implementing Mathematics of Arrays on top of the abstractions we have defined above. In particular,
we decide to have every MoA operation take in and return Arrays. Some higher order operators also
take in callables. The MoA definitions, like those in Lenore's thesis, cannot be translated directly
to this form, because they are often defined as equivalencies on indexing, where as we are defining
things as indeixng on each dimension. Some definitions are easier this way (`OuterProduct`), some are
harder (`Shape`, `Index`). One advantage of doing things this way is we are explicit about all the
partial forms as something is indexed. For example, `Index(<i>, OuterProduct(A, B))` can be reduced,
even if the index does not fully index the result. This is why some definitions are harder, because
we have to think about how the operation is transformed it is partially indexed, instead of thinking
as the index coming in as a full form. For example, `Transpose` is much more complicated, but at the
same time we can partially index a transformed value and this get's reduced.

### Building Python AST (`uarray/ast.py`)

So up to this point, we have just been concerned with expressing arrays and transforming array expressions.
Now we will look at an exmaple of taking some array expression and turning it into a form we can execute
without matchpy. We build up a Python AST using the [`ast`](https://docs.python.org/3/library/ast.html)
core module, where we want to take in and emit NumPy arrays. We could extend this later on to also be able to
emit Python lists, either nested ones, or a flat one in row major form.

First, let's start with the context of this transformation. We
would like to generate some Python AST that is compiled into a
python function that takes some number of numpy arrays as arguments
and returns one.

For our example, let's consider adding two vectors. Our generated code
should look something like this:

```python
import numpy as np

def fn(a, b):
    length = a.shape[0]
    res = np.empty((length,))
    for i in range(length):
        res[i] = a[i] + b[i]
    return res

a = np.arange(10, dtype="float64")
assert np.array_equal(fn(a, a), 2 * a)
```

How would we create this? Let's start with a very manual approach and then
we can show how this can be abstracted properly.

I like to think about this step of the process proceeding in two ways, top down or bottom up.
Starting at the bottom, we can begin with what should be at the leaves of this array expression.
i.e. in the end, where are we indexing into to compute on? Well, if we are generating a function,
then we are indexing into two variables `a` and `b`:

```python
import ast

a_expr = uarray.Expression(ast.Name("a", ast.Load()))
b_expr = uarray.Expression(ast.Name("b", ast.Load()))

a = uarray.NPArray(a_expr)
b = uarray.NPArray(b_expr)
```

<!--
So what are we doing here? We are creating two `NPArray` objects. There should be understood as a
type of Array, but one that is represented by

```
a_vec = ToSequenceWithDim(a, uarray.Int(1))
b_vec = ToSequenceWithDim(b, uarray.Int(1))

length = uarray.Length(a_vec)

i = uarray.Unbound("i")
res = uarray.Sequence(
    length,
    uarray.Function(
        uarray.Add(
            uarray.Content(uarray.CallUnary(uarray.GetItem(a_vec), i)),
            uarray.Content(uarray.CallUnary(uarray.GetItem(b_vec), i)),
        ),
        i
    )
)
``` -->

### Reference

Here we list the categories we are dealing with and then some functors.

We use Python type annotations for the functors, but with catgories as `C/<name>`
to make it clear they don't exist as Python types.

A functor goes from one or more categories to one or more other categories.

- Categories (these don't exist in the code):

  - C/Array
    - Some functors only defined on subcategories of Sequence and Scalar
  - C/Content
  - C/Callable[arg_cats, ret_cats]

    - generic category where you need to specify categories of arguments and return values, below are a list of sub-categories with those arg types specified
    - C/Getitem = C/Callable[(C/Content,), (C/Array,)]
    - C/Initializer = C/Callable[(Identifier), (Statement, ...)]
      - Note: This callable goes from a python identifier to a number of statemnts to fill in that id

  - C/Statement
  - C/Initializable
  - C/NPArray is both C/Initializer and C/Array
  - C/PythonContent is both C/Initializer and C/Content

- Primary Functors (these define the categories/serve as their axioms):

  - GetItem(a: C/Array) -> C/Getitem
    - Partially defined, only on sequences
  - Length(a: C/Array) -> C/Content
    - Partially defined, only on sequences
  - Content(a: C/Array) -> C/Content
    - Partially defined, only on scalars
  - Call(fn: Callable[arg_cats, ret_cats], *arg_cats) -> *ret_cats
  - Initializer(init: C/Initializable) -> C/Initializer

- Operation Constructor functors

  - Sequence(length: C/Content, getitem: C/GetItem) -> C/Array
  - Scalar(content: C/Content) -> C/Array
  - NPArray(init: C/Initializer) -> C/NPArray
  - ToNPArray(a: C/Array, should_allocate: ShouldAllocate) -> C/NPArray
  - ToPythonContent(c: C/Content) -> C/PythonContent
  - DefineFunction(ret: Initializable, \*args: Identifier) -> C/Initializer

- Symbol contructor functors (these take in Python values as arguments)

  - Int(value: Any) -> C/Content
  - Expression(name: str) -> C/Initializer
  - SubstituteStatements(fn: typing.Callable[[ast.AST, ...], C/Initializer, ...])
    -> C/Callable[(Statement, ...), C/Initializer, ...]
  - SubstituteIdentifier(fn: typing.Callable[[Identifer], C/Initializer, ...])
    -> C/Initializer

### Conclusions

This is a large system and on the face of it seems rather convulated. Some of this comes out
of the ambiguity of the answer to "What is an array?"

Sometimes, we know if any array is a scalar of it is not. In that case, we can apply the Mathematics
of Array definitions of operations to
