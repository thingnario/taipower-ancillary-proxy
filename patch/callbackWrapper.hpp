#ifndef PYIEC61850_CALLBACK_WRAPPER_HPP
#define PYIEC61850_CALLBACK_WRAPPER_HPP

#include "iec61850_client.h"
#include <Python.h>


void* transformControlHandlerContext(PyObject* ctx)
{
    static std::map<std::string, PyObject*> s_contexts;
    PyObject* self = NULL;
    PyObject* cb = NULL;
    char *dataObjectPath = NULL;

    if (PyArg_ParseTuple(ctx, "OOs", &self, &cb, &dataObjectPath)) {
        std::map<std::string, PyObject*>::iterator it = s_contexts.find(dataObjectPath);
        if (it != s_contexts.end()) {
            Py_XDECREF(s_contexts[dataObjectPath]);
        }
        Py_XINCREF(ctx);
        s_contexts[dataObjectPath] = ctx;
        return (void *) ctx;
    }

    return NULL;
}

ControlHandlerResult ControlHandlerProxy (ControlAction action, void* parameter, MmsValue* ctlVal, bool test) {
    PyObject* context = (PyObject*)parameter;
    PyObject* self = NULL;
    PyObject* cb = NULL;
    char* dataObject = NULL;
    if (!PyTuple_Check(context) ||
        !PyArg_ParseTuple(context, "OOs", &self, &cb, &dataObject) ||
        !PyCallable_Check(cb)) {
        PyErr_SetString(PyExc_TypeError, "expected a tuple with 2 elements: python callback function and the data object path.");
        return CONTROL_RESULT_FAILED;
    }

    PyObject* args = PyTuple_New(4);
    PyTuple_SetItem(args, 0, SWIG_NewPointerObj(SWIG_as_voidptr(action), SWIGTYPE_p_ControlActionType, 0));
    PyTuple_SetItem(args, 1, PyString_FromString(dataObject));
    PyTuple_SetItem(args, 2, SWIG_NewPointerObj(SWIG_as_voidptr(ctlVal), SWIGTYPE_p_sMmsValue, 0));
    PyTuple_SetItem(args, 3, PyBool_FromLong(test));

    PyGILState_STATE state = PyGILState_Ensure();
    PyObject_CallObject(cb, args);
    PyGILState_Release(state);
}


#endif