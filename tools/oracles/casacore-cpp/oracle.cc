// SPDX-License-Identifier: GPL-3.0-or-later
// The O-cpp oracle of task E6 (research/e6-table-writer-final.md): casacore
// 3.7.1 (KERN-10) performs the cases python-casacore cannot (TiledDataStMan
// hypercubes through TiledDataStManAccessor), the cross-version case X-371
// (C-var's sequence) and the MultiHDF5 refusal input H-mfh5.
//
//     oracle <case> <table> <values-dir>
//
// Tables are made and written through casacore's TableProxy, the class
// python-casacore's `table`, `putcol`, `putcell`, `addrows` and `close`
// call, with the description and dminfo records python-casacore's
// `maketabdesc`, `makearrcoldesc`, `makescacoldesc` and
// `tabledefinehypercolumn` build (field for field, in their order), so the
// two oracles differ only in the casacore version. Values are the raw
// little-endian files `examples/oracle_ms_final.py prepare` writes
// (`<values-dir>/<key>.bin`, NumPy C order); a NumPy shape (n, a, b) is the
// casacore shape [b, a, n]. Keep the sequences in step with the case
// functions of examples/oracle_ms_final.py.
//
// Copyright (C) 2026 Gijs Molenaar. Licensed under the GNU General Public
// License, version 3 or (at your option) any later version; see `LICENSE`.
// It calls casacore (LGPL-2.1-or-later) as a library; nothing is copied
// from it.

#include <casacore/casa/Arrays.h>
#include <casacore/casa/Containers/Record.h>
#include <casacore/casa/Containers/ValueHolder.h>
#include <casacore/tables/DataMan.h>
#include <casacore/tables/DataMan/TiledDataStManAccessor.h>
#include <casacore/tables/Tables.h>
#include <casacore/tables/Tables/TableProxy.h>

#include <chrono>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <vector>

using namespace casacore;

static String g_values;

// The raw bytes of a value file.
static std::vector<char> raw(const String& key) {
  std::ifstream f((g_values + "/" + key + ".bin").c_str(), std::ios::binary);
  if (!f) throw std::runtime_error("missing value file " + key);
  return std::vector<char>((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
}

// An array of casacore shape `shape` from a value file (NumPy C order).
template <class T>
static Array<T> values(const String& key, const IPosition& shape) {
  std::vector<char> b = raw(key);
  if (b.size() != size_t(shape.product()) * sizeof(T)) throw std::runtime_error("size of " + key);
  Array<T> a(shape);
  Bool del;
  T* p = a.getStorage(del);
  memcpy(static_cast<void*>(p), b.data(), b.size());
  a.putStorage(p, del);
  return a;
}

// NumPy Bool values (one byte each).
static Array<Bool> bools(const String& key, const IPosition& shape) {
  std::vector<char> b = raw(key);
  if (b.size() != size_t(shape.product())) throw std::runtime_error("size of " + key);
  Array<Bool> a(shape);
  Bool del;
  Bool* p = a.getStorage(del);
  for (size_t i = 0; i < b.size(); ++i) p[i] = b[i] != 0;
  a.putStorage(p, del);
  return a;
}

static Double scalar(const String& key) { return values<Double>(key, IPosition(1, 1)).data()[0]; }

// python-casacore's makearrcoldesc record (shape in NumPy order).
static Record arrcol(const String& vtype, Int ndim, const std::vector<Int64>& shape) {
  Record r;
  r.define("valueType", vtype);
  r.define("dataManagerType", "");
  r.define("dataManagerGroup", "");
  r.define("ndim", ndim);
  Vector<Int64> s(shape.size());
  for (size_t i = 0; i < shape.size(); ++i) s[i] = shape[i];
  r.define("shape", s);
  r.define("_c_order", True);
  r.define("option", 0);
  r.define("maxlen", 0);
  r.define("comment", "");
  r.defineRecord("keywords", Record());
  return r;
}

// python-casacore's makescacoldesc record.
static Record scacol(const String& vtype) {
  Record r;
  r.define("valueType", vtype);
  r.define("dataManagerType", "");
  r.define("dataManagerGroup", "");
  r.define("option", 0);
  r.define("maxlen", 0);
  r.define("comment", "");
  r.defineRecord("keywords", Record());
  return r;
}

static Vector<String> strings(std::initializer_list<const char*> v) {
  Vector<String> out(v.size());
  size_t i = 0;
  for (const char* s : v) out[i++] = s;
  return out;
}

static Record hypercolumn(Int ndim, Vector<String> data, Vector<String> coord, Vector<String> id) {
  Record h;
  h.define("HCndim", ndim);
  h.define("HCdatanames", data);
  if (coord.size() > 0) h.define("HCcoordnames", coord);
  if (id.size() > 0) h.define("HCidnames", id);
  return h;
}

static Record dminfo1(const String& type, const String& name, const Record& spec, Vector<String> cols) {
  Record m;
  m.define("TYPE", type);
  m.define("NAME", name);
  m.defineRecord("SPEC", spec);
  m.define("COLUMNS", cols);
  Record d;
  d.defineRecord("*1", m);
  return d;
}

static Record lockopt() {
  Record r;
  r.define("option", "permanent");
  return r;
}

static TableProxy* create(const String& path, const Record& desc, const Record& dm, Int64 nrow,
                          const String& endian) {
  return new TableProxy(path, lockopt(), endian, "plain", nrow, desc, dm);
}

static void putcol(TableProxy& t, const String& col, Int64 start, Int64 n, const ValueHolder& v) {
  t.putColumn(col, start, n, 1, v);
}

static void putcell(TableProxy& t, const String& col, Int64 row, const ValueHolder& v) {
  t.putCell(col, Vector<Int64>(1, row), v);
}

// D-cubes and D-be.
static void d_cubes(const String& path, const String& endian) {
  Record desc;
  desc.defineRecord("DATA", arrcol("float", 2, {8, 4}));
  desc.defineRecord("FLAG", arrcol("boolean", 2, {8, 4}));
  desc.defineRecord("FREQ", arrcol("double", 1, {4}));
  desc.defineRecord("TIME", scacol("double"));
  desc.defineRecord("ID", scacol("integer"));
  Record hc;
  hc.defineRecord("TDS", hypercolumn(3, strings({"DATA", "FLAG"}), strings({"FREQ", "", "TIME"}),
                                     strings({"ID"})));
  desc.defineRecord("_define_hypercolumn_", hc);
  Record dm = dminfo1("TiledDataStMan", "TDS", Record(), strings({"DATA", "FLAG", "FREQ", "TIME", "ID"}));
  TableProxy* t = create(path, desc, dm, 11, endian);
  {
    TiledDataStManAccessor acc(t->table(), "TDS");
    Record a;
    a.define("ID", Int(7));
    a.define("FREQ", values<Double>("FREQ.a", IPosition(1, 4)));
    a.define("TIME", values<Double>("TIME.a", IPosition(1, 3)));
    acc.addHypercube(IPosition(3, 4, 8, 3), IPosition(3, 4, 4, 2), a);
    Record b;
    b.define("ID", Int(9));
    acc.addHypercube(IPosition(3, 4, 8, 0), IPosition(3, 2, 8, 2), b);
    Record e1;
    e1.define("ID", Int(9));
    e1.define("TIME", values<Double>("TIME.b", IPosition(1, 2)));
    acc.extendHypercube(2, e1);
    Record e2;
    e2.define("ID", Int(9));
    acc.extendHypercube(4, e2);
    Record c;
    c.define("ID", Int(11));
    c.define("FREQ", values<Double>("FREQ.c", IPosition(1, 4)));
    c.define("TIME", values<Double>("TIME.c", IPosition(1, 2)));
    acc.addHypercube(IPosition(3, 4, 8, 2), IPosition(3, 4, 8, 1), c);
  }
  putcol(*t, "DATA", 0, 11, ValueHolder(values<Float>("DATA", IPosition(3, 4, 8, 11))));
  putcol(*t, "FLAG", 0, 11, ValueHolder(bools("FLAG", IPosition(3, 4, 8, 11))));
  putcell(*t, "TIME", 4, ValueHolder(scalar("TIME4")));
  putcell(*t, "FREQ", 3, ValueHolder(values<Double>("FREQ3", IPosition(1, 4))));
  t->close();
  delete t;
}

static void d_reopen(const String& path) {
  TableProxy* t = new TableProxy(path, lockopt(), Table::Update);
  t->addRow(4);
  {
    TiledDataStManAccessor acc(t->table(), "TDS");
    Record e;
    e.define("ID", Int(9));
    e.define("TIME", values<Double>("TIME.d", IPosition(1, 4)));
    acc.extendHypercube(4, e);
  }
  putcol(*t, "DATA", 11, 4, ValueHolder(values<Float>("DATA", IPosition(3, 4, 8, 4))));
  putcol(*t, "FLAG", 11, 4, ValueHolder(bools("FLAG", IPosition(3, 4, 8, 4))));
  t->close();
  delete t;
}

static void d_multiaxis(const String& path) {
  Record desc;
  desc.defineRecord("DATA", arrcol("complex", 2, {}));
  desc.defineRecord("X", scacol("double"));
  desc.defineRecord("TIME", scacol("double"));
  Record hc;
  hc.defineRecord("TDM", hypercolumn(4, strings({"DATA"}), strings({"", "", "X", "TIME"}),
                                     Vector<String>()));
  desc.defineRecord("_define_hypercolumn_", hc);
  Record dm = dminfo1("TiledDataStMan", "TDM", Record(), strings({"DATA", "X", "TIME"}));
  TableProxy* t = create(path, desc, dm, 0, "little");
  t->addRow(9);
  {
    TiledDataStManAccessor acc(t->table(), "TDM");
    Record a;
    a.define("X", values<Double>("X", IPosition(1, 3)));
    acc.addHypercube(IPosition(4, 4, 2, 3, 0), IPosition(4, 4, 2, 2, 2), a);
    Record e;
    e.define("TIME", values<Double>("TIME", IPosition(1, 3)));
    acc.extendHypercube(3, e);
  }
  putcol(*t, "DATA", 0, 9, ValueHolder(values<Complex>("DATA", IPosition(3, 4, 2, 9))));
  putcell(*t, "X", 4, ValueHolder(scalar("X4")));
  t->close();
  delete t;
}

// X-371: C-var's sequence (examples/oracle_ms_final.py c_var).
static void c_var(const String& path) {
  Record desc;
  desc.defineRecord("D", arrcol("double", 2, {}));
  desc.defineRecord("F", arrcol("float", 2, {}));
  Record spec;
  Vector<Int> tile(2);
  tile[0] = 4;
  tile[1] = 4;
  spec.define("DEFAULTTILESHAPE", tile);
  Record dm = dminfo1("TiledCellStMan", "TCS", spec, strings({"D", "F"}));
  TableProxy* t = create(path, desc, dm, 6, "little");
  putcell(*t, "D", 0, ValueHolder(values<Double>("D0", IPosition(2, 4, 3))));
  putcell(*t, "F", 0, ValueHolder(values<Float>("F0", IPosition(2, 4, 3))));
  putcell(*t, "D", 2, ValueHolder(values<Double>("D2", IPosition(2, 8, 5))));
  putcell(*t, "D", 3, ValueHolder(values<Double>("D3", IPosition(2, 2, 2))));
  putcell(*t, "D", 0, ValueHolder(values<Double>("D0b", IPosition(2, 3, 2))));
  t->addRow(2);
  putcell(*t, "D", 7, ValueHolder(values<Double>("D7", IPosition(2, 2, 2))));
  putcell(*t, "F", 7, ValueHolder(values<Float>("F7", IPosition(2, 2, 2))));
  t->close();
  delete t;
}

// H-mfh5: a 20-row StandardStMan table in a MultiHDF5 container.
static void h_mfh5(const String& path) {
  TableDesc td;
  td.addColumn(ScalarColumnDesc<Int>("I", "", "", ""));
  SetupNewTable newtab(path, td, Table::New, StorageOption(StorageOption::MultiHDF5));
  Table t(newtab, 20);
  ScalarColumn<Int> c(t, "I");
  c.putColumn(Vector<Int>(values<Int>("I", IPosition(1, 20))));
}

int main(int argc, char** argv) {
  if (argc != 4) {
    std::cerr << "usage: oracle <case> <table> <values-dir>" << std::endl;
    return 2;
  }
  String name = argv[1], path = argv[2];
  g_values = argv[3];
  auto start = std::chrono::steady_clock::now();
  try {
    if (name == "D-cubes") d_cubes(path, "little");
    else if (name == "D-be") d_cubes(path, "big");
    else if (name == "D-reopen") d_reopen(path);
    else if (name == "D-multiaxis") d_multiaxis(path);
    else if (name == "X-371") c_var(path);
    else if (name == "H-mfh5") h_mfh5(path);
    else {
      std::cerr << "unknown case " << name << std::endl;
      return 2;
    }
  } catch (std::exception& e) {
    std::cout << name << " FAILED: " << e.what() << std::endl;
    return 1;
  }
  double s = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
  std::cout << name << ": " << s << " s" << std::endl;
  return 0;
}
