import * as bril from './bril-ts/bril.ts';
import {readStdin, unreachable} from './bril-ts/util.ts';

/**
 * An interpreter error to print to the console.
 */
class BriliError extends Error {
  constructor(message?: string) {
    super(message);
    Object.setPrototypeOf(this, new.target.prototype);
    this.name = BriliError.name;
  }
}

/**
 * Create an interpreter error object to throw.
 */
function error(message: string): BriliError {
  return new BriliError(message);
}

/**
 * An abstract key class used to access the heap.
 * This allows for "pointer arithmetic" on keys,
 * while still allowing lookups based on the based pointer of each allocation.
 */
export class Key {
    readonly base: number;
    readonly offset: number;

    constructor(b: number, o: number) {
        this.base = b;
        this.offset = o;
    }

    add(offset: number) {
        return new Key(this.base, this.offset + offset);
    }
}

/**
 * A Heap maps Keys to arrays of a given type.
 */
export class Heap<X> {

    private readonly storage: Map<number, X[]>
    private readonly taint: Map<number, bril.TaintType[]>
    constructor() {
      this.storage = new Map()
      this.taint = new Map()
    }

    isEmpty(): boolean {
      return (this.storage.size == 0) && (this.taint.size == 0);
    }

    private count = 0;
    private getNewBase():number {
      let val = this.count;
      this.count++;
      return val;
    }

    private freeKey(key:Key) {
      return;
    }

    alloc(amt:number): Key {
      if (amt <= 0) {
          throw error(`cannot allocate ${amt} entries`);
      }
      let base = this.getNewBase();
      this.storage.set(base, new Array(amt))
      this.taint.set(base, new Array(amt))
      return new Key(base, 0);
    }

    free(key: Key) {
      if (this.storage.has(key.base) && key.offset == 0) {
        this.freeKey(key);
        this.storage.delete(key.base);
        this.taint.delete(key.base);
      } else {
        throw error(`Tried to free illegal memory location base: ${key.base}, offset: ${key.offset}. Offset must be 0.`);
      }
    }

    write(key: Key, val: X, taint: bril.TaintType) {
      let data = this.storage.get(key.base);
      if (data && data.length > key.offset && key.offset >= 0) {
        data[key.offset] = val;
      } else {
        throw error(`Uninitialized heap location ${key.base} and/or illegal offset ${key.offset}`);
      }
      let taintData = this.taint.get(key.base);
      if (taintData && taintData.length > key.offset && key.offset >= 0) {
        taintData[key.offset] = taint;
      } else {
        throw error(`Uninitialized taint location ${key.base} and/or illegal offset ${key.offset}`);
      }
    }

    read(key: Key): {retVal: X, retTaint: bril.TaintType} {
      let data = this.storage.get(key.base);
      let retVal: X;
      let retTaint: bril.TaintType;
      if (data && data.length > key.offset && key.offset >= 0) {
        retVal = data[key.offset];
      } else {
        throw error(`Uninitialized heap location ${key.base} and/or illegal offset ${key.offset}`);
      }
      let taintData = this.taint.get(key.base);
      if (taintData && taintData.length > key.offset && key.offset >= 0) {
        retTaint = taintData[key.offset];
      } else {
        throw error(`Uninitialized taint location ${key.base} and/or illegal offset ${key.offset}`);
      }
      return {retVal, retTaint};
    }
}

const argCounts: {[key in bril.OpCode]: number | null} = {
  add: 2,
  mul: 2,
  mul_ct: 2,
  sub: 2,
  div: 2,
  div_ct: 2,
  id: 1,
  lt: 2,
  le: 2,
  gt: 2,
  ge: 2,
  eq: 2,
  not: 1,
  and: 2,
  or: 2,
  fadd: 2,
  fadd_ct: 2,
  fmul: 2,
  fmul_ct: 2,
  fsub: 2,
  fsub_ct: 2,
  fdiv: 2,
  fdiv_ct: 2,
  flt: 2,
  flt_ct: 2,
  fle: 2,
  fle_ct: 2,
  fgt: 2,
  fgt_ct: 2,
  fge: 2,
  fge_ct: 2,
  feq: 2,
  feq_ct: 2,
  print: null,  // Any number of arguments.
  br: 1,
  jmp: 0,
  ret: null,  // (Should be 0 or 1.)
  nop: 0,
  call: null,
  alloc: 1,
  free: 1,
  store: 2,
  load: 1,
  ptradd: 2,
  phi: null,
  speculate: 0,
  guard: 1,
  commit: 0,
  ceq: 2,
  clt: 2,
  cle: 2,
  cgt: 2,
  cge: 2,
  char2int: 1,
  int2char: 1,
};

const execCycles: {[key in bril.OpCode]: number} = {
  add: 1,
  mul: 3,
  mul_ct: 3,
  sub: 1,
  div: 3,
  div_ct: 3,
  id: 1,
  lt: 1,
  le: 1,
  gt: 1,
  ge: 1,
  eq: 1,
  not: 1,
  and: 1,
  or: 1,
  fadd: 3,
  fadd_ct: 9,
  fmul: 5,
  fmul_ct: 15,
  fsub: 3,
  fsub_ct: 9,
  fdiv: 5,
  fdiv_ct: 15,
  flt: 3,
  flt_ct: 9,
  fle: 3,
  fle_ct: 9,
  fgt: 3,
  fgt_ct: 9,
  fge: 3,
  fge_ct: 9,
  feq: 3,
  feq_ct: 9,
  print: 1,
  br: 1,
  jmp: 1,
  ret: 1,
  nop: 1,
  call: 1,
  alloc: 1,
  free: 1,
  store: 10,
  load: 10,
  ptradd: 1,
  phi: 0,
  speculate: 0,
  guard: 1,
  commit: 0,
  ceq: 1,
  clt: 1,
  cle: 1,
  cgt: 1,
  cge: 1,
  char2int: 1,
  int2char: 1,
};

type Pointer = {
  loc: Key;
  type: bril.Type;
}

type Value = boolean | BigInt | Pointer | number | string;
type Env = Map<bril.Ident, Value>;

// Add a taint type map
type TaintEnv = Map<bril.Ident, bril.TaintType>;

/**
 * Check whether a run-time value matches the given static type.
 */
function typeCheck(val: Value, typ: bril.Type): boolean {
  if (typ === "int") {
    return typeof val === "bigint";
  } else if (typ === "bool") {
    return typeof val === "boolean";
  } else if (typ === "float") {
    return typeof val === "number";
  } else if (typeof typ === "object" && typ.hasOwnProperty("ptr")) {
    return val.hasOwnProperty("loc");
  } else if (typ === "char") {
    return typeof val === "string";
  }
  throw error(`unknown type ${typ}`);
}

/**
 * Check whether the types are equal.
 */
function typeCmp(lhs: bril.Type, rhs: bril.Type): boolean {
  if (lhs === "int" || lhs == "bool" || lhs == "float" || lhs == "char") {
    return lhs == rhs;
  } else {
    if (typeof rhs === "object" && rhs.hasOwnProperty("ptr")) {
      return typeCmp(lhs.ptr, rhs.ptr);
    } else {
      return false;
    }
  }
}

/**
 * Check numbers are subnormal.
 */
function isSubnormal(num: number): boolean {
  return Math.abs(num) < 1e-10 && Math.abs(num) > 0;
}

function get(env: Env, ident: bril.Ident) {
  let val = env.get(ident);
  if (typeof val === 'undefined') {
    throw error(`undefined variable ${ident}`);
  }
  return val;
}

function get_taint(taintenv: TaintEnv, ident: bril.Ident) {
  let taint = taintenv.get(ident);
  if (typeof taint === 'undefined') {
    throw error(`undefined taint variable ${ident}`);
  }
  return taint;
}

function findFunc(func: bril.Ident, funcs: readonly bril.Function[]) {
  let matches = funcs.filter(function (f: bril.Function) {
    return f.name === func;
  });

  if (matches.length == 0) {
    throw error(`no function of name ${func} found`);
  } else if (matches.length > 1) {
    throw error(`multiple functions of name ${func} found`);
  }

  return matches[0];
}

function alloc(ptrType: bril.ParamType, amt:number, heap:Heap<Value>): Pointer {
  if (typeof ptrType != 'object') {
    throw error(`unspecified pointer type ${ptrType}`);
  } else if (amt <= 0) {
    throw error(`must allocate a positive amount of memory: ${amt} <= 0`);
  } else {
    let loc = heap.alloc(amt)
    let dataType = ptrType.ptr;
    return {
      loc: loc,
      type: dataType
    }
  }
}

/**
 * Ensure that the instruction has exactly `count` arguments,
 * throw an exception otherwise.
 */
function checkArgs(instr: bril.Operation, count: number) {
  let found = instr.args ? instr.args.length : 0;
  if (found != count) {
    throw error(`${instr.op} takes ${count} argument(s); got ${found}`);
  }
}

function getPtr(instr: bril.Operation, env: Env, index: number): Pointer {
  let val = getArgument(instr, env, index);
  if (typeof val !== 'object' || val instanceof BigInt) {
    throw `${instr.op} argument ${index} must be a Pointer`;
  }
  return val;
}

function getArgument(instr: bril.Operation, env: Env, index: number, typ?: bril.Type) {
  let args = instr.args || [];
  if (args.length <= index) {
    throw error(`${instr.op} expected at least ${index+1} arguments; got ${args.length}`);
  }
  let val = get(env, args[index]);
  if (typ && !typeCheck(val, typ)) {
    throw error(`${instr.op} argument ${index} must be a ${typ}`);
  }
  return val;
}

function getInt(instr: bril.Operation, env: Env, index: number): bigint {
  return getArgument(instr, env, index, 'int') as bigint;
}

function getBool(instr: bril.Operation, env: Env, index: number): boolean {
  return getArgument(instr, env, index, 'bool') as boolean;
}

function getFloat(instr: bril.Operation, env: Env, index: number): number {
  return getArgument(instr, env, index, 'float') as number;
}

function getChar(instr: bril.Operation, env: Env, index: number): string {
  return getArgument(instr, env, index, 'char') as string;
}

function getTaint(instr: bril.Operation, taintenv: TaintEnv, index: number): bril.TaintType {
  let args = instr.args || [];
  if (args.length <= index) {
    throw error(`${instr.op} expected at least ${index+1} arguments; got ${args.length}`);
  }
  let taint = taintenv.get(args[index]);
  if (taint === undefined) {
    throw error(`undefined taint variable ${args[index]}`);
  }
  return taint;
}

function getLabel(instr: bril.Operation, index: number): bril.Ident {
  if (!instr.labels) {
    throw error(`missing labels; expected at least ${index+1}`);
  }
  if (instr.labels.length <= index) {
    throw error(`expecting ${index+1} labels; found ${instr.labels.length}`);
  }
  return instr.labels[index];
}

function getFunc(instr: bril.Operation, index: number): bril.Ident {
  if (!instr.funcs) {
    throw error(`missing functions; expected at least ${index+1}`);
  }
  if (instr.funcs.length <= index) {
    throw error(`expecting ${index+1} functions; found ${instr.funcs.length}`);
  }
  return instr.funcs[index];
}

/**
 * The thing to do after interpreting an instruction: this is how `evalInstr`
 * communicates control-flow actions back to the top-level interpreter loop.
 */
type Action =
  {"action": "next"} |  // Normal execution: just proceed to next instruction.
  {"action": "jump", "label": bril.Ident} |
  {"action": "end", "ret": Value | null, "taint": bril.TaintType | null} |
  {"action": "speculate"} |
  {"action": "commit"} |
  {"action": "abort", "label": bril.Ident};
let NEXT: Action = {"action": "next"};

/**
 * The interpreter state that's threaded through recursive calls.
 */
type State = {
  env: Env,
  taintenv: TaintEnv,
  readonly heap: Heap<Value>,
  readonly funcs: readonly bril.Function[],

  // For profiling: 
  // a total count of the number of instructions executed.
  icount: bigint,
  // number of cycles
  ncycles: bigint,

  // For SSA (phi-node) execution: keep track of recently-seen labels.j
  curlabel: string | null,
  lastlabel: string | null,

  // For speculation: the state at the point where speculation began.
  specparent: State | null,
}

/**
 * Interpet a call instruction.
 */
function evalCall(instr: bril.Operation, state: State): Action {
  // Which function are we calling?
  let funcName = getFunc(instr, 0);
  let func = findFunc(funcName, state.funcs);
  if (func === null) {
    throw error(`undefined function ${funcName}`);
  }

  let newEnv: Env = new Map();
  let newTaintEnv: TaintEnv = new Map();

  // Check arity of arguments and definition.
  let params = func.args || [];
  let args = instr.args || [];
  if (params.length !== args.length) {
    throw error(`function expected ${params.length} arguments, got ${args.length}`);
  }

  for (let i = 0; i < params.length; i++) {
    // Look up the variable in the current (calling) environment.
    let value = get(state.env, args[i]);
    // Also look up the taint in the current environment.
    let taint = get_taint(state.taintenv, args[i]);

    // Check argument types
    if (!typeCheck(value, params[i].type)) {
      throw error(`function argument type mismatch`);
    }

    // Set the value of the arg in the new (function) environment.
    newEnv.set(params[i].name, value);
    // Also set the taint of the arg in the new (function) environment.
    newTaintEnv.set(params[i].name, taint);
  }

  // Invoke the interpreter on the function.
  let newState: State = {
    env: newEnv,
    taintenv: newTaintEnv,
    heap: state.heap,
    funcs: state.funcs,
    icount: state.icount,
    ncycles: state.ncycles,
    lastlabel: null,
    curlabel: null,
    specparent: null,  // Speculation not allowed.
  }
  let {retVal, retTaint} = evalFunc(func, newState);
  state.icount = newState.icount;
  state.ncycles = newState.ncycles;

  // Dynamically check the function's return value and type.
  if (!('dest' in instr)) {  // `instr` is an `EffectOperation`.
     // Expected void function
    if (retVal !== null) {
      throw error(`unexpected value returned without destination`);
    }
    if (func.type !== undefined) {
      throw error(`non-void function (type: ${func.type}) doesn't return anything`);
    }
  } else {  // `instr` is a `ValueOperation`.
    // Expected non-void function
    if (instr.type === undefined) {
      throw error(`function call must include a type if it has a destination`);
    }
    if (instr.dest === undefined) {
      throw error(`function call must include a destination if it has a type`);
    }
    if (retVal === null) {
      throw error(`non-void function (type: ${func.type}) doesn't return anything`);
    }
    if (!typeCheck(retVal, instr.type)) {
      throw error(`type of value returned by function does not match destination type`);
    }
    if (func.type === undefined) {
      throw error(`function with void return type used in value call`);
    }
    if (!typeCmp(instr.type, func.type)) {
      throw error(`type of value returned by function does not match declaration`);
    }
    if (retTaint === null) {
      throw error(`non-void function (type: ${func.type}) doesn't return any taint`);
    }
    state.env.set(instr.dest, retVal);
    state.taintenv.set(instr.dest, retTaint);
  }
  return NEXT;
}

/**
 * Interpret an instruction in a given environment, possibly updating the
 * environment. If the instruction branches to a new label, return that label;
 * otherwise, return "next" to indicate that we should proceed to the next
 * instruction or "end" to terminate the function.
 */
function evalInstr(instr: bril.Instruction, state: State): Action {
  // DEBUG: print the instruction
  // console.log(instr);
  state.icount += BigInt(1);
  let args = instr.args || [];

  // Check that we have the right number of arguments.
  if (instr.op !== "const") {
    let count = argCounts[instr.op];
    if (count === undefined) {
      throw error("[argCounts] unknown opcode " + instr.op);
    } else if (count !== null) {
      checkArgs(instr, count);
    }
  }

  // Function calls are not (currently) supported during speculation.
  // It would be cool to add, but aborting from inside a function call
  // would require explicit stack management.
  if (state.specparent && ['call', 'ret'].includes(instr.op)) {
    throw error(`${instr.op} not allowed during speculation`);
  }

  switch (instr.op) {
  case "const":
    // Interpret JSON numbers as either ints or floats.
    let value: Value;
    let taint: bril.TaintType;
    if (typeof instr.value === "number") {
      if (instr.type === "float")
        value = instr.value;
      else
        value = BigInt(Math.floor(instr.value))
    } else if (typeof instr.value === "string") {
      if([...instr.value].length !== 1) throw error(`char must have one character`);
      value = instr.value;
    } else {
      value = instr.value;
    }

    if (typeof instr.type === 'object' && 'taint' in instr.type) {
      taint = instr.type.taint;
    } else {
      // if not specify, the const is public
      taint = "public";
    }

    state.env.set(instr.dest, value);
    state.taintenv.set(instr.dest, taint);
    state.ncycles += BigInt(execCycles["id"]);  // const runs same amount of cycles as id
    return NEXT;

  case "id": {
    let val = getArgument(instr, state.env, 0);
    let taint = getTaint(instr, state.taintenv, 0);
    state.env.set(instr.dest, val);
    state.taintenv.set(instr.dest, taint);
    state.ncycles += BigInt(execCycles["id"]);
    return NEXT;
  }

  case "add": {
    let val = getInt(instr, state.env, 0) + getInt(instr, state.env, 1);
    val = BigInt.asIntN(64, val);
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // one of the taints is private, the result is private
    if (taint0 === "private" || taint1 === "private") {
      state.taintenv.set(instr.dest, "private");
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    state.ncycles += BigInt(execCycles["id"]);
    return NEXT;
  }

  case "mul": {
    // assume mul is unsafe instr
    let lhs = getInt(instr, state.env, 0);
    let rhs = getInt(instr, state.env, 1);
    let val = lhs * rhs;
    val = BigInt.asIntN(64, val);
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // if either of the taints is private, the program leaks private information
    // except for the case where the other input is a public zero
    if ((taint0 === "private" && taint1 === "public" && rhs === BigInt(0))
      || (taint1 === "private" && taint0 === "public" && lhs === BigInt(0))) {
      // declassify the result
      state.taintenv.set(instr.dest, "public");
    } else if (taint0 === "private" || taint1 === "private") {
      throw error(`leak private data through ${instr.op} ${instr.args[0]}(${lhs}, ${taint0}), ${instr.args[1]}(${rhs}, ${taint1})`);
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    // if one of the input is zero, then the execution costs single cycle
    if (lhs === BigInt(0) || rhs === BigInt(0)) {
      state.ncycles += BigInt(1);
    } else {
      state.ncycles += BigInt(execCycles["mul"]);
    }

    return NEXT;
  }

  case "mul_ct": {
    // assume mul is unsafe instr
    let lhs = getInt(instr, state.env, 0);
    let rhs = getInt(instr, state.env, 1);
    let val = lhs * rhs;
    val = BigInt.asIntN(64, val);
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // if either of the taints is private, the program leaks private information
    // except for the case where the other input is a public zero
    if ((taint0 === "private" && taint1 === "public" && rhs === BigInt(0))
      || (taint1 === "private" && taint0 === "public" && lhs === BigInt(0))) {
      // declassify the result
      state.taintenv.set(instr.dest, "public");
    } else if (taint0 === "private" || taint1 === "private") {
      state.taintenv.set(instr.dest, "private");
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    state.ncycles += BigInt(execCycles["mul_ct"]);

    return NEXT;
  }

  case "sub": {
    let val = getInt(instr, state.env, 0) - getInt(instr, state.env, 1);
    val = BigInt.asIntN(64, val);
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // one of the taints is private, the result is private
    if (taint0 === "private" || taint1 === "private") {
      state.taintenv.set(instr.dest, "private");
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    state.ncycles += BigInt(execCycles["sub"]);
    return NEXT;
  }

  case "div": {
    let lhs = getInt(instr, state.env, 0);
    let rhs = getInt(instr, state.env, 1);
    if (rhs === BigInt(0)) {
      throw error(`division by zero`);
    }
    let val = lhs / rhs;
    val = BigInt.asIntN(64, val);
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // if either of the taints is private, the program leaks private information
    // except for the first input is a public zero
    if (taint0 === "public" && lhs === BigInt(0) && taint1 === "private") {
      // declassify the result
      state.taintenv.set(instr.dest, "public");
    } else if (taint0 === "private" || taint1 === "private") {
      throw error(`leak private data through ${instr.op} ${instr.args[0]}(${lhs}, ${taint0}), ${instr.args[1]}(${rhs}, ${taint1})`);
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    // if the first input is zero, then the execution costs single cycle
    if (lhs === BigInt(0)) {
      state.ncycles += BigInt(1);
    } else {
      state.ncycles += BigInt(execCycles["div"]);
    }
    return NEXT;
  }

  case "div_ct": {
    let lhs = getInt(instr, state.env, 0);
    let rhs = getInt(instr, state.env, 1);
    if (rhs === BigInt(0)) {
      throw error(`division by zero`);
    }
    let val = lhs / rhs;
    val = BigInt.asIntN(64, val);
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // if either of the taints is private, the program leaks private information
    // except for the first input is a public zero
    if (taint0 === "public" && lhs === BigInt(0) && taint1 === "private") {
      // declassify the result
      state.taintenv.set(instr.dest, "public");
    } else if (taint0 === "private" || taint1 === "private") {
      state.taintenv.set(instr.dest, "private");
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    state.ncycles += BigInt(execCycles["div_ct"]);

    return NEXT;
  }

  case "le": {
    let val = getInt(instr, state.env, 0) <= getInt(instr, state.env, 1);
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // one of the taints is private, the result is private
    // except for the case where two inputs are the same variable, the output always true
    if (args[0] === args[1]) {
      state.taintenv.set(instr.dest, "public");
    } else if (taint0 === "private" || taint1 === "private") {
      state.taintenv.set(instr.dest, "private");
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    state.ncycles += BigInt(execCycles["le"]);
    return NEXT;
  }

  case "lt": {
    let val = getInt(instr, state.env, 0) < getInt(instr, state.env, 1);
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // one of the taints is private, the result is private
    // except for the case where two inputs are the same variable, the output always false
    if (args[0] === args[1]) {
      state.taintenv.set(instr.dest, "public");
    } else if (taint0 === "private" || taint1 === "private") {
      state.taintenv.set(instr.dest, "private");
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    state.ncycles += BigInt(execCycles["lt"]);
    return NEXT;
  }

  case "gt": {
    let val = getInt(instr, state.env, 0) > getInt(instr, state.env, 1);
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // one of the taints is private, the result is private
    // except for the case where two inputs are the same variable, the output always false
    if (args[0] === args[1]) {
      state.taintenv.set(instr.dest, "public");
    } else if (taint0 === "private" || taint1 === "private") {
      state.taintenv.set(instr.dest, "private");
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    state.ncycles += BigInt(execCycles["gt"]);
    return NEXT;
  }

  case "ge": {
    let val = getInt(instr, state.env, 0) >= getInt(instr, state.env, 1);
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // one of the taints is private, the result is private
    // except for the case where two inputs are the same variable, the output always true
    if (args[0] === args[1]) {
      state.taintenv.set(instr.dest, "public");
    } else if (taint0 === "private" || taint1 === "private") {
      state.taintenv.set(instr.dest, "private");
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    state.ncycles += BigInt(execCycles["ge"]);
    return NEXT;
  }

  case "eq": {
    let val = getInt(instr, state.env, 0) === getInt(instr, state.env, 1);
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // one of the taints is private, the result is private
    // except for the case where two inputs are the same variable, the output always true
    if (args[0] === args[1]) {
      state.taintenv.set(instr.dest, "public");
    } else if (taint0 === "private" || taint1 === "private") {
      state.taintenv.set(instr.dest, "private");
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    state.ncycles += BigInt(execCycles["eq"]);
    return NEXT;
  }

  case "not": {
    let val = !getBool(instr, state.env, 0);
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    // if the input is private, the result is private
    if (taint0 === "private") {
      state.taintenv.set(instr.dest, "private");
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    state.ncycles += BigInt(execCycles["not"]);
    return NEXT;
  }

  case "and": {
    let lhs = getBool(instr, state.env, 0);
    let rhs = getBool(instr, state.env, 1);
    let val = lhs && rhs;
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // one of the taints is private, the result is private
    // except for the case where one of the inputs is public false
    if ((taint0 === "private" && taint1 === "public" && !rhs)
      || (taint1 === "private" && taint0 === "public" && !lhs)) {
      // declassify the result
      state.taintenv.set(instr.dest, "public");
    } else if (taint0 === "private" || taint1 === "private") {
      state.taintenv.set(instr.dest, "private");
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    state.ncycles += BigInt(execCycles["and"]);

    return NEXT;
  }

  case "or": {
    let lhs = getBool(instr, state.env, 0);
    let rhs = getBool(instr, state.env, 1);
    let val = lhs || rhs;
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // one of the taints is private, the result is private
    // except for the case where one of the inputs is public true
    if ((taint0 === "private" && taint1 === "public" && rhs)
      || (taint1 === "private" && taint0 === "public" && lhs)) {
      // declassify the result
      state.taintenv.set(instr.dest, "public");
    } else if (taint0 === "private" || taint1 === "private") {
      state.taintenv.set(instr.dest, "private");
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    state.ncycles += BigInt(execCycles["or"]);
    return NEXT;
  }

  // assume float operations, it is slower when inputs are subnormal numbers
  // we use an artifical def of subnormal number (|x| < 1e-10)
  case "fadd": {
    let lhs = getFloat(instr, state.env, 0);
    let rhs = getFloat(instr, state.env, 1);
    let val = lhs + rhs;
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // one of the taints is private, the result is private
    if (taint0 === "private" || taint1 === "private") {
      throw error(`leak private data through ${instr.op} ${instr.args[0]}(${lhs}, ${taint0}), ${instr.args[1]}(${rhs}, ${taint1})`);
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    // if one more input is subnormal, then the execution cost one more times
    if (isSubnormal(lhs) && isSubnormal(rhs)) {
      state.ncycles += BigInt(3)*BigInt(execCycles["fadd"]);
    } else if (isSubnormal(lhs) || isSubnormal(rhs)) {
      state.ncycles += BigInt(2)*BigInt(execCycles["fadd"]);
    } else {
      state.ncycles += BigInt(execCycles["fadd"]);
    }
    return NEXT;
  }

  case "fadd_ct": {
    let lhs = getFloat(instr, state.env, 0);
    let rhs = getFloat(instr, state.env, 1);
    let val = lhs + rhs;
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // one of the taints is private, the result is private
    if (taint0 === "private" || taint1 === "private") {
      state.taintenv.set(instr.dest, "private");
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    state.ncycles += BigInt(execCycles["fadd_ct"]);
    return NEXT;
  }

  case "fsub": {
    let lhs = getFloat(instr, state.env, 0);
    let rhs = getFloat(instr, state.env, 1);
    let val = lhs - rhs;
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // one of the taints is private, the result is private
    if (taint0 === "private" || taint1 === "private") {
      throw error(`leak private data through ${instr.op} ${instr.args[0]}(${lhs}, ${taint0}), ${instr.args[1]}(${rhs}, ${taint1})`);
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    // if one more input is subnormal, then the execution cost one more times
    if (isSubnormal(lhs) && isSubnormal(rhs)) {
      state.ncycles += BigInt(3)*BigInt(execCycles["fsub"]);
    } else if (isSubnormal(lhs) || isSubnormal(rhs)) {
      state.ncycles += BigInt(2)*BigInt(execCycles["fsub"]);
    } else {
      state.ncycles += BigInt(execCycles["fsub"]);
    }
    return NEXT;
  }

  case "fsub_ct": {
    let lhs = getFloat(instr, state.env, 0);
    let rhs = getFloat(instr, state.env, 1);
    let val = lhs - rhs;
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // one of the taints is private, the result is private
    if (taint0 === "private" || taint1 === "private") {
      state.taintenv.set(instr.dest, "private");
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    state.ncycles += BigInt(execCycles["fsub_ct"]);
    return NEXT;
  }

  case "fmul": {
    let lhs = getFloat(instr, state.env, 0);
    let rhs = getFloat(instr, state.env, 1);
    let val = lhs * rhs;
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // if either of the taints is private, the program leaks private information
    if (taint0 === "private" || taint1 === "private") {
      throw error(`leak private data through ${instr.op} ${instr.args[0]}(${lhs}, ${taint0}), ${instr.args[1]}(${rhs}, ${taint1})`);
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    // if one more input is subnormal, then the execution cost one more times
    if (isSubnormal(lhs) && isSubnormal(rhs)) {
      state.ncycles += BigInt(3)*BigInt(execCycles["fmul"]);
    } else if (isSubnormal(lhs) || isSubnormal(rhs)) {
      state.ncycles += BigInt(2)*BigInt(execCycles["fmul"]);
    } else {
      state.ncycles += BigInt(execCycles["fmul"]);
    }
    return NEXT;
  }

  case "fmul_ct": {
    let lhs = getFloat(instr, state.env, 0);
    let rhs = getFloat(instr, state.env, 1);
    let val = lhs * rhs;
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // if either of the taints is private, the program leaks private information
    if (taint0 === "private" || taint1 === "private") {
      state.taintenv.set(instr.dest, "private");
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    state.ncycles += BigInt(execCycles["fmul_ct"]);
    return NEXT;
  }

  case "fdiv": {
    let lhs = getFloat(instr, state.env, 0);
    let rhs = getFloat(instr, state.env, 1);
    let val = lhs / rhs;
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // if either of the taints is private, the program leaks private information
    if (taint0 === "private" || taint1 === "private") {
      throw error(`leak private data through ${instr.op} ${instr.args[0]}(${lhs}, ${taint0}), ${instr.args[1]}(${rhs}, ${taint1})`);
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    // if one more input is subnormal, then the execution cost one more times
    if (isSubnormal(lhs) && isSubnormal(rhs)) {
      state.ncycles += BigInt(3)*BigInt(execCycles["fdiv"]);
    } else if (isSubnormal(lhs) || isSubnormal(rhs)) {
      state.ncycles += BigInt(2)*BigInt(execCycles["fdiv"]);
    } else {
      state.ncycles += BigInt(execCycles["fdiv"]);
    }
    return NEXT;
  }

  case "fdiv_ct": {
    let lhs = getFloat(instr, state.env, 0);
    let rhs = getFloat(instr, state.env, 1);
    let val = lhs / rhs;
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // if either of the taints is private, the program leaks private information
    if (taint0 === "private" || taint1 === "private") {
      state.taintenv.set(instr.dest, "private");
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    state.ncycles += BigInt(execCycles["fdiv_ct"]);
    return NEXT;
  }

  case "fle": {
    let lhs = getFloat(instr, state.env, 0);
    let rhs = getFloat(instr, state.env, 1);
    let val = lhs <= rhs;
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // one of the taints is private, the result is private
    if (taint0 === "private" || taint1 === "private") {
      throw error(`leak private data through ${instr.op} ${instr.args[0]}(${lhs}, ${taint0}), ${instr.args[1]}(${rhs}, ${taint1})`);
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    // if one more input is subnormal, then the execution cost one more times
    if (isSubnormal(lhs) && isSubnormal(rhs)) {
      state.ncycles += BigInt(3)*BigInt(execCycles["fle"]);
    } else if (isSubnormal(lhs) || isSubnormal(rhs)) {
      state.ncycles += BigInt(2)*BigInt(execCycles["fle"]);
    } else {
      state.ncycles += BigInt(execCycles["fle"]);
    }
    return NEXT;
  }

  case "fle_ct": {
    let lhs = getFloat(instr, state.env, 0);
    let rhs = getFloat(instr, state.env, 1);
    let val = lhs <= rhs;
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // one of the taints is private, the result is private
    if (taint0 === "private" || taint1 === "private") {
      state.taintenv.set(instr.dest, "private");
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    state.ncycles += BigInt(execCycles["fle_ct"]);
    return NEXT;
  }

  case "flt": {
    let lhs = getFloat(instr, state.env, 0);
    let rhs = getFloat(instr, state.env, 1);
    let val = lhs < rhs;
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // one of the taints is private, the result is private
    if (taint0 === "private" || taint1 === "private") {
      throw error(`leak private data through ${instr.op} ${instr.args[0]}(${lhs}, ${taint0}), ${instr.args[1]}(${rhs}, ${taint1})`);
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    // if one more input is subnormal, then the execution cost one more times
    if (isSubnormal(lhs) && isSubnormal(rhs)) {
      state.ncycles += BigInt(3)*BigInt(execCycles["flt"]);
    } else if (isSubnormal(lhs) || isSubnormal(rhs)) {
      state.ncycles += BigInt(2)*BigInt(execCycles["flt"]);
    } else {
      state.ncycles += BigInt(execCycles["flt"]);
    }
    return NEXT;
  }

  case "flt_ct": {
    let lhs = getFloat(instr, state.env, 0);
    let rhs = getFloat(instr, state.env, 1);
    let val = lhs < rhs;
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // one of the taints is private, the result is private
    if (taint0 === "private" || taint1 === "private") {
      state.taintenv.set(instr.dest, "private");
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    state.ncycles += BigInt(execCycles["flt_ct"]);
    return NEXT;
  }

  case "fgt": {
    let lhs = getFloat(instr, state.env, 0);
    let rhs = getFloat(instr, state.env, 1);
    let val = lhs > rhs;
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // one of the taints is private, the result is private
    if (taint0 === "private" || taint1 === "private") {
      throw error(`leak private data through ${instr.op} ${instr.args[0]}(${lhs}, ${taint0}), ${instr.args[1]}(${rhs}, ${taint1})`);
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    // if one more input is subnormal, then the execution cost one more times
    if (isSubnormal(lhs) && isSubnormal(rhs)) {
      state.ncycles += BigInt(3)*BigInt(execCycles["fgt"]);
    } else if (isSubnormal(lhs) || isSubnormal(rhs)) {
      state.ncycles += BigInt(2)*BigInt(execCycles["fgt"]);
    } else {
      state.ncycles += BigInt(execCycles["fgt"]);
    }
    return NEXT;
  }

  case "fgt_ct": {
    let lhs = getFloat(instr, state.env, 0);
    let rhs = getFloat(instr, state.env, 1);
    let val = lhs > rhs;
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // one of the taints is private, the result is private
    if (taint0 === "private" || taint1 === "private") {
      state.taintenv.set(instr.dest, "private");
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    state.ncycles += BigInt(execCycles["fgt_ct"]);
    return NEXT;
  }

  case "fge": {
    let lhs = getFloat(instr, state.env, 0);
    let rhs = getFloat(instr, state.env, 1);
    let val = lhs >= rhs;
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // one of the taints is private, the result is private
    if (taint0 === "private" || taint1 === "private") {
      throw error(`leak private data through ${instr.op} ${instr.args[0]}(${lhs}, ${taint0}), ${instr.args[1]}(${rhs}, ${taint1})`);
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    // if one more input is subnormal, then the execution cost one more times
    if (isSubnormal(lhs) && isSubnormal(rhs)) {
      state.ncycles += BigInt(3)*BigInt(execCycles["fge"]);
    } else if (isSubnormal(lhs) || isSubnormal(rhs)) {
      state.ncycles += BigInt(2)*BigInt(execCycles["fge"]);
    } else {
      state.ncycles += BigInt(execCycles["fge"]);
    }
    return NEXT;
  }

  case "fge_ct": {
    let lhs = getFloat(instr, state.env, 0);
    let rhs = getFloat(instr, state.env, 1);
    let val = lhs >= rhs;
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // one of the taints is private, the result is private
    if (taint0 === "private" || taint1 === "private") {
      state.taintenv.set(instr.dest, "private");
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    state.ncycles += BigInt(execCycles["fge_ct"]);
    return NEXT;
  }

  case "feq": {
    let lhs = getFloat(instr, state.env, 0);
    let rhs = getFloat(instr, state.env, 1);
    let val = lhs === rhs;
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // one of the taints is private, the result is private
    if (taint0 === "private" || taint1 === "private") {
      throw error(`leak private data through ${instr.op} ${instr.args[0]}(${lhs}, ${taint0}), ${instr.args[1]}(${rhs}, ${taint1})`);
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    // if one more input is subnormal, then the execution cost one more times
    if (isSubnormal(lhs) && isSubnormal(rhs)) {
      state.ncycles += BigInt(3)*BigInt(execCycles["feq"]);
    } else if (isSubnormal(lhs) || isSubnormal(rhs)) {
      state.ncycles += BigInt(2)*BigInt(execCycles["feq"]);
    } else {
      state.ncycles += BigInt(execCycles["feq"]);
    }
    return NEXT;
  }

  case "feq_ct": {
    let lhs = getFloat(instr, state.env, 0);
    let rhs = getFloat(instr, state.env, 1);
    let val = lhs === rhs;
    state.env.set(instr.dest, val);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // one of the taints is private, the result is private
    if (taint0 === "private" || taint1 === "private") {
      state.taintenv.set(instr.dest, "private");
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    state.ncycles += BigInt(execCycles["feq_ct"]);
    return NEXT;
  }

  case "print": {
    let args = instr.args || [];
    let values = args.map(function (i) {
      let val = get(state.env, i);
      if (Object.is(-0, val)) { return "-0.00000000000000000" };
      if (typeof val == "number") { return val.toFixed(17) } else {return val.toString()}}
    );
    console.log(...values);
    state.ncycles += BigInt(execCycles["print"]);
    return NEXT;
  }

  case "jmp": {
    state.ncycles += BigInt(execCycles["jmp"]);
    return {"action": "jump", "label": getLabel(instr, 0)};
  }

  case "br": {
    state.ncycles += BigInt(execCycles["br"]);
    let cond = getBool(instr, state.env, 0);
    let taint0 = getTaint(instr, state.taintenv, 0);
    if (taint0 === "private") {
      throw error(`leak private data through ${instr.op} ${instr.args[0]}(${cond}, ${taint0})`);
    }
    if (cond) {
      return {"action": "jump", "label": getLabel(instr, 0)};
    } else {
      return {"action": "jump", "label": getLabel(instr, 1)};
    }
  }

  case "ret": {
    state.ncycles += BigInt(execCycles["ret"]);
    let args = instr.args || [];
    if (args.length == 0) {
      return {"action": "end", "ret": null, "taint": null};
    } else if (args.length == 1) {
      let val = get(state.env, args[0]);
      return {"action": "end", "ret": val, "taint": getTaint(instr, state.taintenv, 0)};
    } else {
      throw error(`ret takes 0 or 1 argument(s); got ${args.length}`);
    }
  }

  case "nop": {
    state.ncycles += BigInt(execCycles["nop"]);
    return NEXT;
  }

  case "call": {
    state.ncycles += BigInt(execCycles["call"]);
    return evalCall(instr, state);
  }

  case "alloc": {
    state.ncycles += BigInt(execCycles["alloc"]);
    let amt = getInt(instr, state.env, 0);
    let typ = instr.type;
    if (!(typeof typ === "object" && typ.hasOwnProperty('ptr'))) {
      throw error(`cannot allocate non-pointer type ${instr.type}`);
    }
    let ptr = alloc(typ, Number(amt), state.heap);
    state.env.set(instr.dest, ptr);
    // alloc returns public type
    state.taintenv.set(instr.dest, "public");
    return NEXT;
  }

  case "free": {
    state.ncycles += BigInt(execCycles["free"]);
    let val = getPtr(instr, state.env, 0);
    state.heap.free(val.loc);
    return NEXT;
  }

  case "store": {
    let target = getPtr(instr, state.env, 0);
    let value = getArgument(instr, state.env, 1, target.type);
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    state.heap.write(target.loc, value, taint1);
    // store leaks private address data (0)
    if (taint0 === "private") {
      throw error(`leak private data through ${instr.op} ${instr.args[0]}(${target}, ${taint0}), ${instr.args[1]}(${value}, ${taint1})`);
    }
    state.ncycles += BigInt(execCycles["store"]);
    return NEXT;
  }

  case "load": {
    let ptr = getPtr(instr, state.env, 0);
    let {retVal, retTaint} = state.heap.read(ptr.loc);
    if (retVal === undefined || retVal === null || retTaint === undefined || retTaint === null) {
      throw error(`Pointer ${instr.args![0]} points to uninitialized data`);
    } else {
      state.env.set(instr.dest, retVal);
      state.taintenv.set(instr.dest, retTaint);
    }
    // load private address data (0)
    let taint0 = getTaint(instr, state.taintenv, 0);
    if (taint0 === "private") {
      throw error(`leak private data through ${instr.op} ${instr.args[0]}(${ptr}, ${taint0})`);
    }
    state.ncycles += BigInt(execCycles["load"]);
    return NEXT;
  }

  case "ptradd": {
    let ptr = getPtr(instr, state.env, 0)
    let val = getInt(instr, state.env, 1)
    state.env.set(instr.dest, { loc: ptr.loc.add(Number(val)), type: ptr.type })
    let taint0 = getTaint(instr, state.taintenv, 0);
    let taint1 = getTaint(instr, state.taintenv, 1);
    // propagate private type
    if (taint0 === "private" || taint1 === "private") {
      state.taintenv.set(instr.dest, "private");
    } else {
      state.taintenv.set(instr.dest, "public");
    }
    state.ncycles += BigInt(execCycles["ptradd"]);
    return NEXT;
  }

  case "phi": {
    let labels = instr.labels || [];
    let args = instr.args || [];
    if (labels.length != args.length) {
      throw error(`phi node has unequal numbers of labels and args`);
    }
    if (!state.lastlabel) {
      throw error(`phi node executed with no last label`);
    }
    let idx = labels.indexOf(state.lastlabel);  // check last label to know where the execution comes from
    if (idx === -1) {
      // Last label not handled. Leave uninitialized.
      state.env.delete(instr.dest);
    } else {
      // Copy the right argument (including an undefined one).
      if (!instr.args || idx >= instr.args.length) {
        throw error(`phi node needed at least ${idx+1} arguments`);
      }
      let src = instr.args[idx];
      let val = state.env.get(src);
      let taint = state.taintenv.get(src);
      if (val === undefined) {
        state.env.delete(instr.dest);
        state.taintenv.delete(instr.dest);
      } else {
        state.env.set(instr.dest, val);
        state.taintenv.set(instr.dest, taint);
      }
    }
    state.ncycles += BigInt(execCycles["phi"]);
    return NEXT;
  }

  // Begin speculation.
  case "speculate": {
    return {"action": "speculate"};
  }

  // Abort speculation if the condition is false.
  case "guard": {
    if (getBool(instr, state.env, 0)) {
      return NEXT;
    } else {
      return {"action": "abort", "label": getLabel(instr, 0)};
    }
  }

  // Resolve speculation, making speculative state real.
  case "commit": {
    return {"action": "commit"};
  }

  case "ceq": {
    let lhs = getChar(instr, state.env, 0);
    let rhs = getChar(instr, state.env, 1);
    let val = lhs === rhs;
    state.env.set(instr.dest, val);
    // propagate private type, except for the case where two inputs are the same variable
    if (args[0] === args[1]) {
      state.taintenv.set(instr.dest, "public");
    } else {
      let taint0 = getTaint(instr, state.taintenv, 0);
      let taint1 = getTaint(instr, state.taintenv, 1);
      if (taint0 === "private" || taint1 === "private") {
        state.taintenv.set(instr.dest, "private");
      } else {
        state.taintenv.set(instr.dest, "public");
      }
    }
    state.ncycles += BigInt(execCycles["ceq"]);
    return NEXT;
  }

  case "clt": {
    let lhs = getChar(instr, state.env, 0);
    let rhs = getChar(instr, state.env, 1);
    let val = lhs < rhs;
    state.env.set(instr.dest, val);
    // propagate private type, except for the case where two inputs are the same variable
    if (args[0] === args[1]) {
      state.taintenv.set(instr.dest, "public");
    } else {
      let taint0 = getTaint(instr, state.taintenv, 0);
      let taint1 = getTaint(instr, state.taintenv, 1);
      if (taint0 === "private" || taint1 === "private") {
        state.taintenv.set(instr.dest, "private");
      } else {
        state.taintenv.set(instr.dest, "public");
      }
    }
    state.ncycles += BigInt(execCycles["clt"]);
    return NEXT;
  }

  case "cle": {
    let lhs = getChar(instr, state.env, 0);
    let rhs = getChar(instr, state.env, 1);
    let val = lhs <= rhs;
    state.env.set(instr.dest, val);
    // propagate private type, except for the case where two inputs are the same variable
    if (args[0] === args[1]) {
      state.taintenv.set(instr.dest, "public");
    } else {
      let taint0 = getTaint(instr, state.taintenv, 0);
      let taint1 = getTaint(instr, state.taintenv, 1);
      if (taint0 === "private" || taint1 === "private") {
        state.taintenv.set(instr.dest, "private");
      } else {
        state.taintenv.set(instr.dest, "public");
      }
    }
    state.ncycles += BigInt(execCycles["cle"]);
    return NEXT;
  }

  case "cgt": {
    let lhs = getChar(instr, state.env, 0);
    let rhs = getChar(instr, state.env, 1);
    let val = lhs > rhs;
    state.env.set(instr.dest, val);
    // propagate private type, except for the case where two inputs are the same variable
    if (args[0] === args[1]) {
      state.taintenv.set(instr.dest, "public");
    } else {
      let taint0 = getTaint(instr, state.taintenv, 0);
      let taint1 = getTaint(instr, state.taintenv, 1);
      if (taint0 === "private" || taint1 === "private") {
        state.taintenv.set(instr.dest, "private");
      } else {
        state.taintenv.set(instr.dest, "public");
      }
    }
    state.ncycles += BigInt(execCycles["cgt"]);
    return NEXT;
  }

  case "cge": {
    let lhs = getChar(instr, state.env, 0);
    let rhs = getChar(instr, state.env, 1);
    let val = lhs >= rhs;
    state.env.set(instr.dest, val);
    // propagate private type, except for the case where two inputs are the same variable
    if (args[0] === args[1]) {
      state.taintenv.set(instr.dest, "public");
    } else {
      let taint0 = getTaint(instr, state.taintenv, 0);
      let taint1 = getTaint(instr, state.taintenv, 1);
      if (taint0 === "private" || taint1 === "private") {
        state.taintenv.set(instr.dest, "private");
      } else {
        state.taintenv.set(instr.dest, "public");
      }
    }
    state.ncycles += BigInt(execCycles["cge"]);
    return NEXT;
  }

  case "char2int": {
    let code = getChar(instr, state.env, 0).codePointAt(0);
    let val = BigInt.asIntN(64, BigInt(code as number));
    state.env.set(instr.dest, val);
    // directly propagate taint
    let taint = getTaint(instr, state.taintenv, 0);
    state.taintenv.set(instr.dest, taint);
    state.ncycles += BigInt(execCycles["char2int"]);
    return NEXT;
  }

  case "int2char": {
    let i = getInt(instr, state.env, 0);
    if (i > 1114111 || i < 0 || (55295 < i && i < 57344)) {
      throw error(`value ${i} cannot be converted to char`);
    }
    let val = String.fromCodePoint(Number(i));
    state.env.set(instr.dest, val);
    let taint = getTaint(instr, state.taintenv, 0);
    state.taintenv.set(instr.dest, taint);
    state.ncycles += BigInt(execCycles["int2char"]);
    return NEXT;
  }

  }
  unreachable(instr);
  throw error(`unhandled opcode ${(instr as any).op}`);
}

function evalFunc(func: bril.Function, state: State): { retVal: Value | null, retTaint: bril.TaintType | null } {
  for (let i = 0; i < func.instrs.length; ++i) {
    let line = func.instrs[i];
    if ('op' in line) {
      // Run an instruction.
      let action = evalInstr(line, state);

      // Take the prescribed action.
      switch (action.action) {
      case 'end': {
        // Return from this function.
        return {retVal: action.ret, retTaint: action.taint};
      }
      case 'speculate': {
        // Begin speculation.
        state.specparent = {...state};
        state.env = new Map(state.env);
        break;
      }
      case 'commit': {
        // Resolve speculation.
        if (!state.specparent) {
          throw error(`commit in non-speculative state`);
        }
        state.specparent = null;
        break;
      }
      case 'abort': {
        // Restore state.
        if (!state.specparent) {
          throw error(`abort in non-speculative state`);
        }
        // We do *not* restore `icount` from the saved state to ensure that we
        // count "aborted" instructions.
        Object.assign(state, {
          env: state.specparent.env,
          lastlabel: state.specparent.lastlabel,
          curlabel: state.specparent.curlabel,
          specparent: state.specparent.specparent,
        });
        break;
      }
      case 'next':
      case 'jump':
        break;
      default:
        unreachable(action);
        throw error(`unhandled action ${(action as any).action}`);
      }
      // Move to a label.
      if ('label' in action) {
        // Search for the label and transfer control.
        for (i = 0; i < func.instrs.length; ++i) {
          let sLine = func.instrs[i];
          if ('label' in sLine && sLine.label === action.label) {
            --i;  // Execute the label next.
            break;
          }
        }
        if (i === func.instrs.length) {
          throw error(`label ${action.label} not found`);
        }
      }
    } else if ('label' in line) {
      // Update CFG tracking for SSA phi nodes.
      state.lastlabel = state.curlabel;
      state.curlabel = line.label;
    }
  }

  // Reached the end of the function without hitting `ret`.
  if (state.specparent) {
    throw error(`implicit return in speculative state`);
  }
  return null;
}

function parseChar(s: string): string {
  let c = s;
  if ([...c].length === 1) {
    return c;
  } else {
    throw error(`char argument to main must have one character; got ${s}`);
  }
}

function parseBool(s: string): boolean {
  if (s === 'true') {
    return true;
  } else if (s === 'false') {
    return false;
  } else {
    throw error(`boolean argument to main must be 'true'/'false'; got ${s}`);
  }
}

function parseNumber(s: string): number {
  let f = parseFloat(s);
  // parseFloat and Number have subtly different behaviors for parsing strings
    // parseFloat ignores all random garbage after any valid number
    // Number accepts empty/whitespace only strings and rejects numbers with seperators
  // Use both and only accept the intersection of the results?
  let f2 = Number(s);
  if (!isNaN(f) && f === f2) {
    return f;
  } else {
    throw error(`float argument to main must not be 'NaN'; got ${s}`);
  }
}

function parseMainArguments(expected: bril.Argument[], args: string[]) : { newEnv: Env, newTaintEnv: TaintEnv } {
  let newEnv: Env = new Map();
  let newTaintEnv: TaintEnv = new Map();

  if (args.length !== expected.length) {
    throw error(`mismatched main argument arity: expected ${expected.length}; got ${args.length}`);
  }

  for (let i = 0; i < args.length; i++) {
    let primetype = expected[i].type.prim;
    if (primetype === undefined) {
      primetype = expected[i].type;
    }
    let taint = expected[i].type.taint;
    // for main func args, if taint is not specified, default to private
    if (taint === undefined) {
      taint = "private";
    }
    newTaintEnv.set(expected[i].name, taint as bril.TaintType);
    switch (primetype) {
      case "int":
        // https://dev.to/darkmavis1980/you-should-stop-using-parseint-nbf
        let n: bigint = BigInt(Number(args[i]));
        newEnv.set(expected[i].name, n as Value);
        break;
      case "float":
        let f: number = parseNumber(args[i]);
        newEnv.set(expected[i].name, f as Value);
        break;
      case "bool":
        let b: boolean = parseBool(args[i]);
        newEnv.set(expected[i].name, b as Value);
        break;
      case "char":
        let c: string = parseChar(args[i]);
        newEnv.set(expected[i].name, c as Value);
        break;
    }
  }
  return {newEnv: newEnv, newTaintEnv: newTaintEnv};
}

function evalProg(prog: bril.Program) {
  let heap = new Heap<Value>()
  let main = findFunc("main", prog.functions);
  if (main === null) {
    console.warn(`no main function defined, doing nothing`);
    return;
  }

  // Silly argument parsing to find the `-p` flag.
  let args: string[] = Array.from(Deno.args);
  let profiling = false;
  let pidx = args.indexOf('-p');
  if (pidx > -1) {
    profiling = true;
    args.splice(pidx, 1);
  }

  // Remaining arguments are for the main function.k
  let expected = main.args || [];
  let {newEnv, newTaintEnv} = parseMainArguments(expected, args);

  let state: State = {
    funcs: prog.functions,
    heap,
    env: newEnv,
    taintenv: newTaintEnv,
    icount: BigInt(0),
    ncycles: BigInt(0),
    lastlabel: null,
    curlabel: null,
    specparent: null,
  }
  evalFunc(main, state);

  if (!heap.isEmpty()) {
    throw error(`Some memory locations have not been freed by end of execution.`);
  }

  if (profiling) {
    console.error(`total_dyn_inst: ${state.icount}`);
    console.error(`total_exec_cycles: ${state.ncycles}`);
  }

}

async function main() {
  try {
    let prog = JSON.parse(await readStdin()) as bril.Program;
    evalProg(prog);
  }
  catch(e) {
    if (e instanceof BriliError) {
      console.error(`error: ${e.message}`);
      Deno.exit(2);
    } else {
      throw e;
    }
  }
}

main();
