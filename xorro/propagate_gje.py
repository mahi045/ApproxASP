from . import util
from . import gje
from itertools import chain
import clingo

def reason_gje(columns, assignment):
    state = {}
    partial = []
    deduced_literals = []

    ## Get Partial Assignment
    state["parity"] = columns["parity"]
    for lit, column in columns.items():
        if lit != "parity":
            value = assignment.value(lit)
            if value == None:
                state[lit] = column
            elif value == True:
                state["parity"] = gje.xor_columns(column, state["parity"])
                partial.append( lit)
            elif value == False:
                partial.append(-lit)

    ## Build the matrix from columns state
    matrix, xor_lits = gje.columns_state_to_matrix(state)

    ## If there are more than unary xors perform GJE
    if len(state) > 2:
        matrix = gje.remove_rows_zeros(matrix)
        matrix = gje.perform_gauss_jordan_elimination(matrix)

    ## Check SATISFIABILITY
    conflict = gje.check_sat(matrix)
    if not conflict and xor_lits:
        ## Imply literals
        deduced_literals = gje.deduce_clause(matrix, xor_lits)

    return conflict, partial, deduced_literals


def lits_to_binary(columns, lits, constraint):
    for i in range(len(lits)):
        if lits[i] in constraint:
            columns.setdefault(lits[i], []).append(1)
        elif -lits[i] in constraint:
            columns.setdefault(lits[i], []).append(1)
        else:
            columns.setdefault(lits[i], []).append(0)
    return columns


class Propagate_GJE:
    def __init__(self):
        self.__states  = []

    def init(self, init):
        """
        Initializes xor constraints based on the symbol table to build a binary matrix.
        This propagator is called on fixpoints to perform Gauss-Jordan Elimination after Unit Propagation
        """
        for thread_id in range(len(self.__states), init.number_of_threads):
            self.__states.append({})
        
        init.check_mode = clingo.PropagatorCheckMode.Fixpoint
        literals = []
        ## Get the constraints
        ret = util.symbols_to_xor_r(init.symbolic_atoms, util.default_get_lit(init))
        if ret is not None:
            constraints, facts = ret
            constraints.extend([fact] for fact in facts)

            ## Get the literals and parities
            for constraint in constraints:
                even = False
                if constraint[0] < 0:
                    even = True
                for lit in constraint:
                    if abs(lit) not in literals:
                        literals.append(abs(lit))
                for thread_id in range(init.number_of_threads):
                    if even:
                        self.__states[thread_id].setdefault("parity", []).append(0)
                    else:
                        self.__states[thread_id].setdefault("parity", []).append(1)

            ## Build the rest of the matrix
            for constraint in constraints:
                for thread_id in range(init.number_of_threads):
                    self.__states[thread_id] = lits_to_binary(self.__states[thread_id], sorted(literals), constraint)

    def check(self, control):
        """
        Check if current assignment is conflict-free, detect a conflict or deduce literals
        by doing Gauss-Jordan Elimination
        """
        if self.__states[control.thread_id]:
            columns = self.__states[control.thread_id]
            ## GJE
            conflict, partial, clause = reason_gje(columns, control.assignment)
            if clause is not None:
                for lit in clause:
                    if not control.add_nogood(partial+[-lit]) or not control.propagate():
                        return
            if conflict:
                if not control.add_nogood(partial) or not control.propagate():
                    return


