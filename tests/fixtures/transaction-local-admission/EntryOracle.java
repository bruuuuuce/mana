import java.io.*;
import java.util.*;
import javax.tools.*;
import javax.lang.model.element.*;
import com.sun.source.tree.*;
import com.sun.source.util.*;

/** Independent metadata probe: reports syntax/symbols, never decides admission. */
public class EntryOracle {
    public static void main(String[] args) throws Exception {
        final int[] errors={0};
        JavaCompiler compiler=ToolProvider.getSystemJavaCompiler();
        try(StandardJavaFileManager fm=compiler.getStandardFileManager(null,Locale.ROOT,null)) {
            JavacTask task=(JavacTask)compiler.getTask(new StringWriter(),fm,d->{if(d.getKind()==Diagnostic.Kind.ERROR)errors[0]++;},
                Arrays.asList("-proc:none","-implicit:none","-source","8","-target","8","-classpath",args[0],"-sourcepath",args[1]),
                null,fm.getJavaFileObjects(Arrays.copyOfRange(args,3,args.length)));
            List<CompilationUnitTree> units=new ArrayList<CompilationUnitTree>();
            for(CompilationUnitTree unit:task.parse())units.add(unit);
            task.analyze();
            final Trees trees=Trees.instance(task);
            final long start=Long.parseLong(args[2]);
            for(final CompilationUnitTree unit:units)new TreePathScanner<Void,Void>() {
                @Override public Void visitMethod(MethodTree m,Void p) {
                    if(trees.getSourcePositions().getStartPosition(unit,m)!=start)return super.visitMethod(m,p);
                    ExecutableElement caller=(ExecutableElement)trees.getElement(getCurrentPath());
                    StatementTree first=m.getBody().getStatements().get(0);
                    System.out.println("FIRST_STATEMENT="+first.getKind());
                    ExpressionTree init=first instanceof VariableTree?((VariableTree)first).getInitializer():null;
                    if(init instanceof MethodInvocationTree) {
                        MethodInvocationTree call=(MethodInvocationTree)init;
                        TreePath path=TreePath.getPath(unit,call);
                        ExecutableElement target=(ExecutableElement)trees.getElement(path);
                        System.out.println("CALL_START="+trees.getSourcePositions().getStartPosition(unit,call));
                        System.out.println("CALL_END="+trees.getSourcePositions().getEndPosition(unit,call));
                        System.out.println("SELECT_KIND="+call.getMethodSelect().getKind());
                        System.out.println("TARGET_PRIVATE="+target.getModifiers().contains(Modifier.PRIVATE));
                        System.out.println("TARGET_STATIC="+target.getModifiers().contains(Modifier.STATIC));
                        System.out.println("TARGET_SYNCHRONIZED="+target.getModifiers().contains(Modifier.SYNCHRONIZED));
                        System.out.println("TARGET_NATIVE="+target.getModifiers().contains(Modifier.NATIVE));
                        System.out.println("SAME_OWNER="+caller.getEnclosingElement().equals(target.getEnclosingElement()));
                        for(int i=0;i<call.getArguments().size();i++) {
                            ExpressionTree arg=call.getArguments().get(i);
                            TreePath ap=TreePath.getPath(unit,arg);
                            Element e=trees.getElement(ap);
                            System.out.println("ARG_"+i+"="+arg.getKind()+":"+caller.getParameters().indexOf(e)+":"+
                                task.getTypes().isSameType(trees.getTypeMirror(ap),target.getParameters().get(i).asType())+
                                (arg instanceof LiteralTree?":"+((LiteralTree)arg).getValue():""));
                        }
                    }
                    return null;
                }
            }.scan(unit,null);
            System.out.println("ERRORS="+errors[0]);
        }
    }
}
