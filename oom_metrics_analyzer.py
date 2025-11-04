"""
OOM Metrics Analyzer for Python projects
Calculates: WMC, DIT, NOC, CBO, RFC, LCOM, Maintainability Index (MI approximate), Polymorphism Factor (PF), Method Inheritance Factor (MIF)

Usage:
    python oom_metrics_analyzer.py /path/to/python/project

Notes / Limitations:
- Works on Python source only (.py).
- Best-effort static analysis using the ast module; may miss dynamic features (duck typing, dynamic imports, eval).
- Halstead metrics are approximated by counting AST token types as operators/operands.

"""
import os
import sys
import ast
import math
from collections import defaultdict, Counter

# ---------- Utilities ----------

def iter_py_files(root):
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            if f.endswith('.py'):
                yield os.path.join(dirpath, f)


# ---------- AST Visitors ----------

class ClassInfo:
    def __init__(self, name, node, filepath):
        self.name = name
        self.node = node
        self.filepath = filepath
        self.methods = {}  # name -> ast.FunctionDef
        self.attributes = set()
        self.bases = []  # base class names (as strings)
        self.called_classes = set()  # for CBO
        self.called_methods = set()  # for RFC
        self.overrides = set()


class Analyzer(ast.NodeVisitor):
    def __init__(self, filepath):
        self.filepath = filepath
        self.classes = {}  # name -> ClassInfo
        self.current_class = None
        self.current_method = None
        # Halstead helpers
        self.operators = Counter()
        self.operands = Counter()

    def visit_ClassDef(self, node: ast.ClassDef):
        ci = ClassInfo(node.name, node, self.filepath)
        # bases
        for b in node.bases:
            if isinstance(b, ast.Name):
                ci.bases.append(b.id)
            elif isinstance(b, ast.Attribute):
                # e.g., module.Base
                ci.bases.append(b.attr)
            else:
                ci.bases.append(ast.unparse(b) if hasattr(ast, 'unparse') else '?')
        self.classes[node.name] = ci
        # traverse methods
        prev_class = self.current_class
        self.current_class = ci
        self.generic_visit(node)
        self.current_class = prev_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        if self.current_class is not None:
            self.current_class.methods[node.name] = node
            prev_method = self.current_method
            self.current_method = node.name
            self.generic_visit(node)
            self.current_method = prev_method
        else:

            # top-level function — still count for Halstead
            prev_method = self.current_method
            self.current_method = None
            self.generic_visit(node)
            self.current_method = prev_method

    def visit_Attribute(self, node: ast.Attribute):
        # attribute access like self.x or OtherClass.method
        # consider attribute as operand
        self.operands[str(node.attr)] += 1
        # if attribute is class-name-like, consider for CBO
        if isinstance(node.value, ast.Name) and node.value.id != 'self':
            if self.current_class:
                self.current_class.called_classes.add(node.value.id)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # function/method calls
        func = node.func
        if isinstance(func, ast.Attribute):
            # obj.method()
            if isinstance(func.value, ast.Name) and func.value.id == 'self':
                # calling own method
                if self.current_class:
                    self.current_class.called_methods.add(func.attr)
            else:
                if self.current_class and isinstance(func.value, ast.Name):
                    self.current_class.called_classes.add(func.value.id)
            self.operators['call.' + func.attr] += 1
        elif isinstance(func, ast.Name):
            self.operators['call.' + func.id] += 1
        else:
            self.operators['call.unknown'] += 1
        # operands: args
        for a in node.args:
            if isinstance(a, ast.Constant):
                self.operands[str(a.value)] += 1
            elif isinstance(a, ast.Name):
                self.operands[a.id] += 1
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
        # treat targets and value tokens
        for t in node.targets:
            if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == 'self':
                # self.attr assignment -> attribute
                if self.current_class:
                    self.current_class.attributes.add(t.attr)
            elif isinstance(t, ast.Name):
                self.operands[t.id] += 1
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name):
        # operator/operand heuristic
        if isinstance(node.ctx, ast.Load):
            self.operands[node.id] += 1
        self.generic_visit(node)

    def visit_If(self, node: ast.If):
        self.operators['if'] += 1
        self.generic_visit(node)

    def visit_For(self, node: ast.For):
        self.operators['for'] += 1
        self.generic_visit(node)

    def visit_While(self, node: ast.While):
        self.operators['while'] += 1
        self.generic_visit(node)

    def visit_Try(self, node: ast.Try):
        self.operators['try'] += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp):
        # and/or
        self.operators['boolop'] += 1
        self.generic_visit(node)

    def visit_Return(self, node: ast.Return):
        self.operators['return'] += 1
        self.generic_visit(node)


# ---------- Metric Calculators ----------

def cyclomatic_complexity(func_node: ast.FunctionDef) -> int:
    # CC = 1 + number of decision points inside function
    counter = 0
    for node in ast.walk(func_node):
        if isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.ExceptHandler, ast.BoolOp)):
            counter += 1
        # conditional expressions
        if isinstance(node, ast.IfExp):
            counter += 1
    return max(1, 1 + counter)


def halstead_volume(operators: Counter, operands: Counter):
    N1 = sum(operators.values())
    N2 = sum(operands.values())
    n1 = len(operators)
    n2 = len(operands)
    N = N1 + N2
    n = n1 + n2
    if n == 0 or N == 0:
        return 0.0
    try:
        V = N * math.log2(max(2, n))
        return V
    except Exception:
        return N * math.log2(n+1)


# LCOM (Henderson-Sellers/Chidamber-Kemerer style simplified)
def lcom_of_class(ci: ClassInfo):
    methods = list(ci.methods.values())
    m = len(methods)
    if m <= 1:
        return 0
    # collect attributes used by each method: look for 'self.X' in method body
    method_attrs = []
    for fn in methods:
        attrs = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == 'self':
                attrs.add(node.attr)
        method_attrs.append(attrs)
    P = 0
    Q = 0
    for i in range(m):
        for j in range(i+1, m):
            if method_attrs[i].isdisjoint(method_attrs[j]):
                P += 1
            else:
                Q += 1
    lcom = P - Q
    return lcom if lcom > 0 else 0


# DIT & NOC: need whole-project graph

# ---------- Project-wide aggregator ----------

def analyze_project(root):
    analyzers = {}
    for path in iter_py_files(root):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                src = f.read()
            tree = ast.parse(src, filename=path)
            an = Analyzer(path)
            an.visit(tree)
            analyzers[path] = an
        except Exception as e:
            print(f"Warning: failed to parse {path}: {e}")

    # collect classes across project
    classes = {}  # name -> ClassInfo
    for an in analyzers.values():
        for cname, ci in an.classes.items():
            # if same class name defined multiple times, append path
            key = f"{cname}@{ci.filepath}"
            classes[key] = ci

    # build name->key map for simple resolution
    name_to_keys = defaultdict(list)
    for key, ci in classes.items():
        name_to_keys[ci.name].append(key)

    # compute DIT (depth within known project inheritance only)
    def compute_dit(key, visited=None):
        if visited is None:
            visited = set()
        if key in visited:
            return 0
        visited.add(key)
        ci = classes[key]
        if not ci.bases:
            return 1
        max_depth = 1
        for b in ci.bases:
            # try resolving base to a key
            if b in name_to_keys:
                # pick first match
                base_key = name_to_keys[b][0]
                d = 1 + compute_dit(base_key, visited)
                if d > max_depth:
                    max_depth = d
            else:
                # unknown base, assume external (depth 1)
                max_depth = max(max_depth, 2)
        return max_depth

    dit_map = {}
    for key in classes:
        dit_map[key] = compute_dit(key)

    # NOC: count immediate subclasses present in project
    noc_map = {k: 0 for k in classes}
    for key, ci in classes.items():
        for b in ci.bases:
            if b in name_to_keys:
                for base_key in name_to_keys[b]:
                    noc_map[base_key] += 1

    # WMC, CBO, RFC, LCOM
    metrics = {}
    total_operators = Counter()
    total_operands = Counter()
    for key, ci in classes.items():
        wmc = 0
        cbo = set()
        rfc_set = set()
        for mname, mnode in ci.methods.items():
            cc = cyclomatic_complexity(mnode)
            wmc += cc
            # calls -> called methods
            # we've stored called_methods and called_classes in Analyzer but Analyzer instance is per-file
        # compute CBO from Analyzer info: combine called_classes across methods
        # Need to find the Analyzer that had this class
        called_classes = ci.called_classes
        cbo = set(called_classes) - {ci.name}
        # RFC = number of methods + number of distinct methods called
        rfc = len(ci.methods) + len(ci.called_methods)
        lcom = lcom_of_class(ci)
        metrics[key] = {
            'WMC': wmc,
            'CBO': len(cbo),
            'RFC': rfc,
            'LCOM': lcom,
            'DIT': dit_map.get(key, 1),
            'NOC': noc_map.get(key, 0),
            'methods': list(ci.methods.keys()),
            'attributes': list(ci.attributes),
            'called_classes': list(ci.called_classes),
            'called_methods': list(ci.called_methods),
            'filepath': ci.filepath,
        }
        # accumulate halstead tokens from file-level analyzers
        # find Analyzer for filepath
        for an in analyzers.values():
            if an.filepath == ci.filepath:
                total_operators.update(an.operators)
                total_operands.update(an.operands)

    # Halstead Volume
    V = halstead_volume(total_operators, total_operands)

    # MI calculation per file/project (we'll compute a project-level MI)
    # LOC: count non-empty non-comment lines
    loc = 0
    for path in iter_py_files(root):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    s = line.strip()
                    if s and not s.startswith('#'):
                        loc += 1
        except Exception:
            pass

    # Cyclomatic complexity project-level: sum of WMCs
    total_cc = sum(m['WMC'] for m in metrics.values())
    # Comment percentage (approx): comments / total lines
    total_lines = 0
    comment_lines = 0
    for path in iter_py_files(root):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    total_lines += 1
                    if line.strip().startswith('#'):
                        comment_lines += 1
        except Exception:
            pass
    comment_pct = 0
    if total_lines:
        comment_pct = (comment_lines / total_lines) * 100

    # MI formula
    if V <= 0 or loc <= 0:
        MI = 0.0
    else:
        try:
            MI = 171 - 5.2 * math.log(max(1e-6, V)) - 0.23 * (total_cc) - 16.2 * math.log(max(1, loc)) + 0.99 * comment_pct
        except Exception:
            MI = 0.0

    # Polymorphism Factor (PF): fraction of overridden methods among possible overrides
    overridden = 0
    total_methods = 0
    for key, ci in classes.items():
        total_methods += len(ci.methods)
        # check if a method overrides a base method
        for b in ci.bases:
            if b in name_to_keys:
                base_key = name_to_keys[b][0]
                base_ci = classes.get(base_key)
                if base_ci:
                    for m in ci.methods:
                        if m in base_ci.methods:
                            overridden += 1
    PF = (overridden / total_methods) if total_methods else 0.0

    # Method Inheritance Factor (MIF): ratio of inherited methods to total methods available
    inherited_methods = 0
    available_methods = 0
    for key, ci in classes.items():
        own = len(ci.methods)
        inherited = 0
        for b in ci.bases:
            if b in name_to_keys:
                base_key = name_to_keys[b][0]
                base_ci = classes.get(base_key)
                if base_ci:
                    inherited += len(base_ci.methods)
        inherited_methods += inherited
        available_methods += own + inherited
    MIF = (inherited_methods / available_methods) if available_methods else 0.0

    return metrics, {
        'Halstead_Volume': V,
        'LOC': loc,
        'Total_CC': total_cc,
        'Comment_pct': comment_pct,
        'MI': MI,
        'PF': PF,
        'MIF': MIF,
    }


# ---------- CLI ----------

def print_report(metrics, summary):
    print('\nObject-Oriented Metrics Report')
    print('-------------------------------------')
    print(f"Project Maintainability Index (MI): {summary['MI']:.2f}")
    print(f"Halstead Volume (approx): {summary['Halstead_Volume']:.2f}")
    print(f"Total Cyclomatic Complexity: {summary['Total_CC']}")
    print(f"LOC (approx, non-blank non-comment): {summary['LOC']}")
    print(f"Polymorphism Factor (PF): {summary['PF']:.3f}")
    print(f"Method Inheritance Factor (MIF): {summary['MIF']:.3f}")
    print('\nClass-level metrics:')
    print('{:40} {:>5} {:>5} {:>5} {:>5} {:>5} {:>5}'.format('Class@file', 'WMC', 'DIT', 'NOC', 'CBO', 'RFC', 'LCOM'))
    for key, m in metrics.items():
        short = f"{key}" if len(key) < 38 else (key[:34] + '...')
        print('{:40} {:5} {:5} {:5} {:5} {:5} {:5}'.format(short, m['WMC'], m['DIT'], m['NOC'], m['CBO'], m['RFC'], m['LCOM']))


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python oom_metrics_analyzer.py /path/to/python/project')
        sys.exit(1)
    root = sys.argv[1]
    metrics, summary = analyze_project(root)
    print_report(metrics, summary)
    print('\nNotes: This is a static, heuristic-based analyzer for Python sources.\n')