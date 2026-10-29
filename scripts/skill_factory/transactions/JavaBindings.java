import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import javax.tools.*;
import javax.lang.model.element.*;
import javax.lang.model.type.*;
import com.sun.source.tree.*;
import com.sun.source.util.*;

/** Opt-in attribution only. No generate/call, processors, or target class loading. */
public final class JavaBindings {
    static Trees trees;
    static Path root;
    static int nodes, depth, maxNodes, maxDepth;
    static boolean errors;
    static List<Object> diagnostics = new ArrayList<Object>();
    static Set<String> selected = new TreeSet<String>();
    static Map<String,TreePath> declarations = new TreeMap<String,TreePath>();
    static List<Object> relations = new ArrayList<Object>();
    static Map<String,Object> obj(Object... a) { return JavaFacts.obj(a); }
    static final class Budget extends RuntimeException { private static final long serialVersionUID=1L; }
    static class Bounded extends TreePathScanner<Void,Void> {
        @Override public Void scan(Tree tree, Void p) {
            if (tree==null) return null;
            if (++nodes>maxNodes || ++depth>maxDepth) throw new Budget();
            try { return super.scan(tree,p); } finally { depth--; }
        }
    }
    static Map<String,Object> evidence(TreePath path) {
        CompilationUnitTree u=path.getCompilationUnit(); Tree t=path.getLeaf();
        long start=trees.getSourcePositions().getStartPosition(u,t);
        long end=trees.getSourcePositions().getEndPosition(u,t);
        if (start<0 || end<start) return null;
        return obj("file",root.relativize(Paths.get(u.getSourceFile().toUri())).toString().replace(File.separatorChar,'/'),
            "start",start,"end",end,"line",u.getLineMap().getLineNumber(start));
    }
    static boolean valid(TypeMirror t,int d) {
        if (t==null || d>16) return false;
        switch(t.getKind()) {
            case ERROR: case OTHER: case NONE: return false;
            case ARRAY: return valid(((ArrayType)t).getComponentType(),d+1);
            case DECLARED:
                for(TypeMirror a:((DeclaredType)t).getTypeArguments()) if(!valid(a,d+1))return false;
                return true;
            case EXECUTABLE:
                ExecutableType e=(ExecutableType)t;
                if(!valid(e.getReturnType(),d+1))return false;
                for(TypeMirror a:e.getParameterTypes())if(!valid(a,d+1))return false;
                for(TypeMirror a:e.getThrownTypes())if(!valid(a,d+1))return false;
                return true;
            // Generic variables/captures are outside this increment.
            case TYPEVAR: case WILDCARD: case INTERSECTION: return false;
            default: return true;
        }
    }
    static String typeIdentity(TypeMirror t) {
        if(t instanceof DeclaredType) {
            Element e=((DeclaredType)t).asElement();
            if(e instanceof TypeElement)return ((TypeElement)e).getQualifiedName().toString();
        }
        return "";
    }
    static String identity(Element e) {
        if(e instanceof TypeElement)return ((TypeElement)e).getQualifiedName().toString();
        if(e instanceof ExecutableElement) {
            ExecutableElement m=(ExecutableElement)e;
            List<String> p=new ArrayList<String>();
            for(VariableElement a:m.getParameters())p.add(a.asType().toString());
            return identity(m.getEnclosingElement())+"#"+m.getSimpleName()+"("+String.join(",",p)+")";
        }
        return "";
    }
    static boolean supported(String name) {
        TreePath p=declarations.get(name);
        return p!=null && ((ClassTree)p.getLeaf()).getModifiers().getFlags().contains(Modifier.STATIC);
    }
    static Map<String,Object> relation(String kind,TreePath p,Element e,String dependency) {
        TypeMirror type=trees.getTypeMirror(p);
        boolean ok=!errors && supported(dependency) && e!=null && valid(e.asType(),0) && valid(type,0);
        TreePath declaration=e==null?null:trees.getPath(e);
        Map<String,Object> fact=obj("relation",kind,"dependency",dependency,"site",evidence(p),
            "status",ok?"VERIFIED":"UNRESOLVED",
            "reason",ok?"STATIC_BINDING_ONLY":errors?"ATTRIBUTION_ERRORS":!supported(dependency)?"NON_STATIC_OR_ABSENT_MEMBER":"MISSING_OR_UNSUPPORTED_BINDING",
            "target",ok?identity(e):null,"expressionType",ok?type.toString():null,
            "declaration",ok && declaration!=null?evidence(declaration):null,
            "runtimeDispatch","UNKNOWN");
        relations.add(fact);return fact;
    }
    static void run(String[] args) throws Exception {
        root=Paths.get(args[0]); String entryFile=args[1]; long entryStart=Long.parseLong(args[2]);
        maxNodes=Integer.parseInt(args[3]);maxDepth=Integer.parseInt(args[4]);
        selected.addAll(Arrays.asList(args[5].split(",")));selected.remove("");
        String release=args[6], cp=args[7];
        JavaCompiler compiler=ToolProvider.getSystemJavaCompiler();
        DiagnosticListener<JavaFileObject> listener=d -> {
            if(d.getKind()==Diagnostic.Kind.ERROR) {
                errors=true;
                if(diagnostics.size()<128)diagnostics.add(obj("code",d.getCode(),"line",d.getLineNumber()));
            }
        };
        StandardJavaFileManager fm=compiler.getStandardFileManager(listener,Locale.ROOT,StandardCharsets.UTF_8);
        try {
            List<String> options=new ArrayList<String>(Arrays.asList("-proc:none","-implicit:none","-encoding","UTF-8",
                "-classpath",cp,"-sourcepath",root.resolve("empty").toString(),"-Xmaxerrs","128"));
            if(System.getProperty("java.specification.version").equals("1.8")) {
                if(!release.equals("8"))throw new IllegalArgumentException();
                options.addAll(Arrays.asList("-source","8","-target","8"));
            } else options.addAll(Arrays.asList("--release",release));
            // Compiler textual diagnostics are deliberately discarded; listener is allowlisted.
            Writer sink=new Writer(){public void write(char[] c,int o,int n){} public void flush(){} public void close(){}};
            boolean execution=args.length>8 && args[8].equals("--execution");
            boolean localEntry=args.length>8 && args[8].equals("--local-entry");
            JavacTask task=(JavacTask)compiler.getTask(sink,fm,listener,options,null,
                fm.getJavaFileObjects(Arrays.copyOfRange(args,(execution || localEntry)?9:8,args.length)));
            trees=Trees.instance(task);
            List<CompilationUnitTree> units=new ArrayList<CompilationUnitTree>();
            final TreePath[] entry={null};
            for(CompilationUnitTree unit:task.parse()) {
                units.add(unit);
                new Bounded(){
                    String owner=unit.getPackageName()==null?"":unit.getPackageName().toString();
                    @Override public Void visitClass(ClassTree c,Void p) {
                        String previous=owner;
                        owner=owner.isEmpty()?c.getSimpleName().toString():owner+"."+c.getSimpleName();
                        if(selected.contains(owner) && getCurrentPath().getParentPath().getLeaf() instanceof ClassTree)
                            declarations.put(owner,getCurrentPath());
                        try{return super.visitClass(c,p);}finally{owner=previous;}
                    }
                    @Override public Void visitMethod(MethodTree m,Void p) {
                        Map<String,Object> ev=evidence(getCurrentPath());
                        if(ev!=null && ev.get("file").equals(entryFile) && ((Number)ev.get("start")).longValue()==entryStart)
                            entry[0]=getCurrentPath();
                        return super.visitMethod(m,p);
                    }
                }.scan(unit,null);
            }
            task.analyze(); // Never call generate() or CompilationTask.call().
            List<Object> types=new ArrayList<Object>();
            for(String name:selected) {
                TreePath path=declarations.get(name);
                if(path==null){types.add(obj("identity",name,"status","ABSENT","reason","DECLARATION_NOT_IN_BOUNDED_INPUT"));continue;}
                ClassTree c=(ClassTree)path.getLeaf(); Element element=trees.getElement(path);
                TypeElement t=element instanceof TypeElement?(TypeElement)element:null;
                boolean ok=!errors && supported(name) && t!=null && valid(t.asType(),0);
                List<Object> parents=new ArrayList<Object>(),members=new ArrayList<Object>();
                List<Tree> ownParents=new ArrayList<Tree>();
                if(c.getExtendsClause()!=null)ownParents.add(c.getExtendsClause());ownParents.addAll(c.getImplementsClause());
                for(Tree parent:ownParents) {
                    TreePath pp=new TreePath(path,parent);TypeMirror tm=trees.getTypeMirror(pp);
                    boolean resolved=ok && valid(tm,0);
                    parents.add(obj("relation","TYPE_INHERITANCE","declaredType",JavaFacts.typeSyntax(parent),
                        "target",resolved?tm.toString():null,"status",resolved?"VERIFIED":"UNRESOLVED","evidence",evidence(pp)));
                }
                if(t!=null)for(Element m:t.getEnclosedElements())if(m instanceof ExecutableElement) {
                    TreePath mp=trees.getPath(m);Map<String,Object> ev=mp==null?null:evidence(mp);
                    // Generated default constructors have no complete source span.
                    boolean resolved=ok && valid(m.asType(),0) && ev!=null;
                    String declaredSignature=null,declaredReturnType=null;
                    if(ev!=null && mp.getLeaf() instanceof MethodTree) {
                        MethodTree syntax=(MethodTree)mp.getLeaf();List<String> parameters=new ArrayList<String>();
                        for(VariableTree parameter:syntax.getParameters())parameters.add(JavaFacts.typeSyntax(parameter.getType()));
                        declaredSignature=name+"#"+syntax.getName()+"("+String.join(",",parameters)+")";
                        declaredReturnType=syntax.getReturnType()==null?null:JavaFacts.typeSyntax(syntax.getReturnType());
                    }
                    members.add(obj("identity",resolved?identity(m):null,"status",resolved?"VERIFIED":"UNRESOLVED",
                        "declaredSignature",declaredSignature,"declaredReturnType",declaredReturnType,
                        "reason",ev==null?"IMPLICIT_OR_BINARY_DECLARATION":"DECLARATION_ONLY",
                        "evidence",ev));
                }
                types.add(obj("identity",name,"owner",name.substring(0,name.lastIndexOf('.')),
                    "relation","TYPE_CONTAINMENT","modifiers",JavaFacts.flags(c.getModifiers()),
                    "status",ok?"VERIFIED":"UNRESOLVED","reason",errors?"ATTRIBUTION_ERRORS":!supported(name)?"NON_STATIC_MEMBER":"DECLARATION_ONLY",
                    "evidence",evidence(path),"parents",parents,"members",members));
            }
            if(entry[0]!=null)new Bounded(){
                void reference() {
                    Element e=trees.getElement(getCurrentPath());
                    if(e instanceof TypeElement && selected.contains(identity(e)))
                        relation("TYPE_REFERENCE",getCurrentPath(),e,identity(e));
                }
                @Override public Void visitIdentifier(IdentifierTree t,Void p){reference();return super.visitIdentifier(t,p);}
                @Override public Void visitMemberSelect(MemberSelectTree t,Void p){reference();return super.visitMemberSelect(t,p);}
                void invocation() {
                    Element e=trees.getElement(getCurrentPath());
                    if(!(e instanceof ExecutableElement))return;
                    String owner=identity(e.getEnclosingElement());
                    String result=typeIdentity(trees.getTypeMirror(getCurrentPath()));
                    String receiver="";
                    Tree call=getCurrentPath().getLeaf();
                    if(call instanceof MethodInvocationTree) {
                        ExpressionTree select=((MethodInvocationTree)call).getMethodSelect();
                        if(select instanceof MemberSelectTree) {
                            TreePath sp=new TreePath(getCurrentPath(),select);
                            receiver=typeIdentity(trees.getTypeMirror(new TreePath(sp,((MemberSelectTree)select).getExpression())));
                        }
                    }
                    String dep=selected.contains(owner)?owner:selected.contains(result)?result:selected.contains(receiver)?receiver:null;
                    if(dep!=null)relation("EXECUTION_DEPENDENCY",getCurrentPath(),e,dep);
                }
                @Override public Void visitMethodInvocation(MethodInvocationTree t,Void p){invocation();return super.visitMethodInvocation(t,p);}
                @Override public Void visitNewClass(NewClassTree t,Void p){invocation();return super.visitNewClass(t,p);}
                @Override public Void visitVariable(VariableTree v,Void p) {
                    TypeMirror type=trees.getTypeMirror(new TreePath(getCurrentPath(),v.getType()));
                    String dep=typeIdentity(type);
                    if(selected.contains(dep) && v.getInitializer()!=null) {
                        TreePath init=new TreePath(getCurrentPath(),v.getInitializer());
                        Element e=trees.getElement(init);
                        Map<String,Object> fact=relation("VALUE_PRODUCTION",init,e instanceof ExecutableElement?e:null,dep);
                        fact.put("valueDeclaration",evidence(getCurrentPath()));
                        fact.put("typeSite",evidence(new TreePath(getCurrentPath(),v.getType())));
                    }
                    return super.visitVariable(v,p);
                }
                @Override public Void visitClass(ClassTree c,Void p){return null;} // no local/anonymous bodies
            }.scan(entry[0],null);
            Map<String,Object> output=obj("status",entry[0]==null?"BLOCKED":errors?"INCOMPLETE":"COMPLETE",
                "reason",entry[0]==null?"ENTRY_ABSENT":errors?"ATTRIBUTION_ERRORS":"STATIC_BINDINGS_ONLY",
                "types",types,"relations",relations,"diagnostics",diagnostics,"nodes",nodes,
                "runtime",obj("javaVersion",System.getProperty("java.version"),"vendor",System.getProperty("java.vendor"),
                    "languageVersion",System.getProperty("java.specification.version")));
            if(execution && entry[0]!=null)output.put("execution",JavaExecution.collect(entry[0]));
            if(localEntry && entry[0]!=null)output.put("localEntry",JavaLocalEntry.collect(entry[0]));
            output.put("nodes",nodes);
            System.out.println(JavaFacts.json(output));
        } finally {fm.close();}
    }
    public static void main(String[] args) {
        try {run(args);} catch(Budget e) {
            System.out.println("{\"status\":\"BLOCKED\",\"reason\":\"NODE_OR_DEPTH_BUDGET\",\"types\":[],\"relations\":[],\"diagnostics\":[]}");
        } catch(Throwable e) {
            // Includes resource exhaustion and javac failures; no source-bearing exception text.
            System.out.println("{\"status\":\"BLOCKED\",\"reason\":\"ATTRIBUTION_FAILED\",\"types\":[],\"relations\":[],\"diagnostics\":[]}");
        }
    }
}
