import java.io.*;
import java.util.*;
import javax.tools.*;
import javax.lang.model.element.*;
import com.sun.source.tree.*;
import com.sun.source.util.*;

/** Independent test oracle, no Mana imports. Parse/analyze only; metadata only. */
public class ExecutionOracle {
    static Trees trees;
    static CompilationUnitTree unit;
    static String caller;
    static String quote(String s) {
        return s==null?"null":"\""+s.replace("\\","\\\\").replace("\"","\\\"")+"\"";
    }
    static String identity(Element e) {
        if(e instanceof TypeElement)return ((TypeElement)e).getQualifiedName().toString();
        if(e instanceof ExecutableElement) {
            List<String> parameters=new ArrayList<String>();
            for(VariableElement p:((ExecutableElement)e).getParameters())parameters.add(p.asType().toString());
            return identity(e.getEnclosingElement())+"#"+e.getSimpleName()+"("+String.join(",",parameters)+")";
        }
        return null;
    }
    static String position(TreePath p) {
        return "\"start\":"+trees.getSourcePositions().getStartPosition(unit,p.getLeaf())+
            ",\"end\":"+trees.getSourcePositions().getEndPosition(unit,p.getLeaf());
    }
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler=ToolProvider.getSystemJavaCompiler();
        final int[] errors={0};
        try(StandardJavaFileManager fm=compiler.getStandardFileManager(null,Locale.ROOT,null)) {
            JavacTask task=(JavacTask)compiler.getTask(new StringWriter(),fm,d->{
                if(d.getKind()==Diagnostic.Kind.ERROR) {
                    errors[0]++;
                    System.out.println("{\"diagnostic\":"+quote(d.getCode())+"}");
                }
            },Arrays.asList("-proc:none","-implicit:none","-source","8","-target","8",
                "-classpath",args[0],"-sourcepath",args[1],"-Xmaxerrs","128"),null,
                fm.getJavaFileObjects(Arrays.copyOfRange(args,2,args.length)));
            trees=Trees.instance(task);
            List<CompilationUnitTree> units=new ArrayList<CompilationUnitTree>();
            for(CompilationUnitTree u:task.parse())units.add(u);
            task.analyze();
            for(CompilationUnitTree u:units) {
                unit=u;
                new TreePathScanner<Void,Void>() {
                    @Override public Void visitMethod(MethodTree m,Void p) {
                        String prior=caller;caller=identity(trees.getElement(getCurrentPath()));
                        System.out.println("{\"kind\":\"METHOD\",\"identity\":"+quote(caller)+
                            ",\"bodyAvailable\":"+(m.getBody()!=null)+","+position(getCurrentPath())+"}");
                        try{return super.visitMethod(m,p);}finally{caller=prior;}
                    }
                    void emit() {
                        Element e=trees.getElement(getCurrentPath());
                        if(!(e instanceof ExecutableElement))return;
                        ExecutableElement method=(ExecutableElement)e;
                        TreePath declaration=trees.getPath(e);
                        boolean body=declaration!=null && declaration.getLeaf() instanceof MethodTree &&
                            ((MethodTree)declaration.getLeaf()).getBody()!=null &&
                            trees.getSourcePositions().getEndPosition(declaration.getCompilationUnit(),declaration.getLeaf())>=0;
                        String dispatch=e.getKind()==ElementKind.CONSTRUCTOR?"CONSTRUCTOR":
                            method.getModifiers().contains(Modifier.STATIC)?"STATIC":
                            method.getModifiers().contains(Modifier.PRIVATE)?"DIRECT":"VIRTUAL";
                        System.out.println("{\"kind\":\"CALL\",\"caller\":"+quote(caller)+
                            ",\"target\":"+quote(identity(e))+",\"dispatch\":"+quote(dispatch)+
                            ",\"bodyAvailable\":"+body+","+position(getCurrentPath())+"}");
                    }
                    @Override public Void visitMethodInvocation(MethodInvocationTree m,Void p){emit();return super.visitMethodInvocation(m,p);}
                    @Override public Void visitNewClass(NewClassTree m,Void p){emit();return super.visitNewClass(m,p);}
                }.scan(u,null);
            }
            System.out.println("{\"errors\":"+errors[0]+"}");
        }
    }
}
