import os,sys
sys.path.insert(0,"/home/twf/mdsplus-tdishr/mdsobjects/python/build/lib")
try:
    reload(MDSplus)
    print "reloaded"
except:
    import MDSplus
print MDSplus.__file__
MDSplus.Data.usePython=True

def resultStr(good):
    if good:
        return "Test result: Suc"+"cess" ### so you can search for good results
    else:
        return "Test result: Fai"+"led" ### so you can search for bad results
    
def TdiEvaluate(arg):
    old=MDSplus.Data.usePython
    MDSplus.Data.usePython=False
    try:
        ans=MDSplus.tdibuiltins.EVALUATE(arg).evaluate()
    finally:
        MDSplus.Data.usePython=old
    return ans

def testEvaluate(expr_text,nodoc=False):
    """Test evaluation of expression. Test consists of:
        Compile with python and tdishr and compare the results
        Evaluate with python and tdishr and compare the results
        print __doc__ string of the builtin if True
    """
    MDSplus.Data.usePython=True
    MDSplus.Data.debug=False
    MDSplus.Data.showTdi=True
    try:
        exp=MDSplus.Data.compile(expr_text)
        print(exp)
        MDSplus.Data.usePython=False
        exptdi=MDSplus.Data.compile(expr_text)
        MDSplus.Data.usePython=True
        if not exp.compare(exptdi):
            print("""%s
    Compile result differed
        Python produced: %s,%s
        TDISHR produced: %s,%s
""" % (resultStr(False),str(exp.decompile()),str(type(exp)),str(exptdi.decompile()),str(type(exptdi))))
        else:
            print exp
            ans=exp.evaluate()
            MDSplus.Data.usePython=False
            print exp
            tdians=exp.evaluate()
            MDSplus.Data.usePython=True
            if not ans.compare(tdians):
                print("""%s
    Evaluate result differed
        Python produced: %s
        TDISHR produced: %s
""" % (resultStr(False),str(ans.decompile()),str(tdians.decompile())))
            else:
                print(resultStr(True))
                print(exp.evaluate().decompile())
    except:
        print(resultStr(False))
        raise
    if not nodoc:
        print(exp.__doc__)
testEvaluate('ACHAR(BUILD_SIGNAL([88,89,90],*,*))',nodoc=True)

