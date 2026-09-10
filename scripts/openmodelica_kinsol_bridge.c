#define _GNU_SOURCE

#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>

/*
 * Keep the full OpenModelica runtime local and expose only the three nonlinear
 * entry points missing from an OMC_MINIMAL_RUNTIME FMU.  DATA and solver
 * structures remain owned by the FMU; the bridge uses the ABI from the exact
 * same pinned OpenModelica image.
 */

static void *runtime_handle = NULL;

static void fail(const char *message)
{
  fprintf(stderr, "OPENMODELICA_KINSOL_BRIDGE_FAIL: %s\n", message);
  abort();
}

static void *runtime_symbol(const char *name)
{
  if (runtime_handle == NULL) {
    const char *path = getenv("FMU_RUNTIME_LIBRARY");
    int flags = RTLD_NOW | RTLD_LOCAL;
#ifdef RTLD_DEEPBIND
    flags |= RTLD_DEEPBIND;
#endif
    if (path == NULL || path[0] == '\0') {
      fail("FMU_RUNTIME_LIBRARY is not set");
    }
    runtime_handle = dlopen(path, flags);
    if (runtime_handle == NULL) {
      fail(dlerror());
    }
  }

  dlerror();
  void *symbol = dlsym(runtime_handle, name);
  const char *error = dlerror();
  if (error != NULL || symbol == NULL) {
    fail(error != NULL ? error : name);
  }
  return symbol;
}

void initializeNonlinearSystemData(
  void *data,
  void *thread_data,
  void *nonlinear_system,
  int system_number,
  int *is_sparse,
  int *is_big)
{
  typedef void (*function_type)(void *, void *, void *, int, int *, int *);
  static function_type function = NULL;
  if (function == NULL) {
    function = (function_type)runtime_symbol("initializeNonlinearSystemData");
  }
  function(data, thread_data, nonlinear_system, system_number, is_sparse, is_big);
}

int solve_nonlinear_system(void *data, void *thread_data, int system_number)
{
  typedef int (*function_type)(void *, void *, int);
  static function_type function = NULL;
  if (function == NULL) {
    function = (function_type)runtime_symbol("solve_nonlinear_system");
  }
  return function(data, thread_data, system_number);
}

void freeNonlinearSyst(void *data, void *thread_data, void *nonlinear_system)
{
  typedef void (*function_type)(void *, void *, void *);
  static function_type function = NULL;
  if (function == NULL) {
    function = (function_type)runtime_symbol("freeNonlinearSyst");
  }
  function(data, thread_data, nonlinear_system);
}
