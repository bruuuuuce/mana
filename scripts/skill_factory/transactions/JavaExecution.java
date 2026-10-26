import java.util.*;
import javax.lang.model.element.*;
import com.sun.source.tree.*;
import com.sun.source.util.*;

/** Bounded metadata projection using the SAME attributed javac task as HYBRID.
 * Not a CFG, runtime resolver, or transaction traversal authorization.
 */
final class JavaExecution {
    static Map<String,Object> obj(Object... args) { return JavaBindings.obj(args); }
    static Map<String,TreePath> pending=new LinkedHashMap<String,TreePath>();
    static List<Object> methods=new ArrayList<Object>(), sites=new ArrayList<Object>();
    static Set<String> seen=new HashSet<String>();
    static boolean incomplete=false;

    static boolean admitted(Element e) {
        if(!(e instanceof ExecutableElement))return false;
        String owner=JavaBindings.identity(e.getEnclosingElement());
        return JavaBindings.selected.contains(owner);
    }
    static List<String> initialization(Element owner) {
        List<String> limits=new ArrayList<String>();
        TreePath path=JavaBindings.trees.getPath(owner);
        if(path==null || !(path.getLeaf() instanceof ClassTree)) {
            limits.add("OWNER_BODY_UNAVAILABLE");return limits;
        }
        ClassTree cls=(ClassTree)path.getLeaf();
        for(Tree member:cls.getMembers()) {
            if(member instanceof BlockTree)limits.add("CLASS_OR_INSTANCE_INITIALIZER");
            if(member instanceof VariableTree && ((VariableTree)member).getInitializer()!=null)
                limits.add("FIELD_INITIALIZER");
        }
        if(owner.getEnclosingElement() instanceof TypeElement && !owner.getModifiers().contains(Modifier.STATIC))
            limits.add("ENCLOSING_INSTANCE_UNKNOWN");
        return new ArrayList<String>(new TreeSet<String>(limits));
    }
    static String dispatch(ExecutableElement e) {
        if(e.getKind()==ElementKind.CONSTRUCTOR)return "CONSTRUCTOR";
        if(e.getModifiers().contains(Modifier.STATIC))return "STATIC";
        if(e.getModifiers().contains(Modifier.PRIVATE))return "DIRECT";
        return "VIRTUAL";
    }
    static boolean exact(ExecutableElement e) {
        return !dispatch(e).equals("VIRTUAL") || e.getModifiers().contains(Modifier.PRIVATE)
            || e.getModifiers().contains(Modifier.FINAL)
            || e.getEnclosingElement().getModifiers().contains(Modifier.FINAL);
    }
    static List<Object> transaction(ExecutableElement e) {
        List<Object> result=new ArrayList<Object>();
        for(AnnotationMirror a:e.getAnnotationMirrors()) {
            if(!a.getAnnotationType().toString().equals("org.springframework.transaction.annotation.Transactional"))continue;
            String propagation="REQUIRED";
            for(Map.Entry<? extends ExecutableElement,? extends AnnotationValue> v:a.getElementValues().entrySet())
                if(v.getKey().getSimpleName().toString().equals("propagation")) {
                    Object value=v.getValue().getValue();
                    propagation=value instanceof VariableElement?((VariableElement)value).getSimpleName().toString():"UNKNOWN";
                }
            if(!Arrays.asList("REQUIRED","REQUIRES_NEW","NESTED","SUPPORTS","NOT_SUPPORTED","MANDATORY","NEVER").contains(propagation))propagation="UNKNOWN";
            result.add(obj("annotation",a.getAnnotationType().toString(),"propagation",propagation,
                "interception","UNKNOWN","effect","NOT_ASSERTED"));
        }
        return result;
    }
    static void scan(final TreePath path,final boolean root,final int level) {
        Element caller=JavaBindings.trees.getElement(path);
        if(!(caller instanceof ExecutableElement)) {incomplete=true;return;}
        final String callerId=JavaBindings.identity(caller);
        final List<String> hazards=new ArrayList<String>();
        MethodTree m=(MethodTree)path.getLeaf();
        if(m.getBody()==null)hazards.add("BODY_UNAVAILABLE");
        else for(StatementTree statement:m.getBody().getStatements()) {
            if(statement instanceof ReturnTree && ((ReturnTree)statement).getExpression()==null)continue;
            if(!(statement instanceof ExpressionStatementTree) ||
                !(((ExpressionStatementTree)statement).getExpression() instanceof MethodInvocationTree))
                hazards.add("UNSUPPORTED_"+statement.getKind().toString());
        }
        hazards.addAll(initialization(caller.getEnclosingElement()));
        if(caller.getKind()==ElementKind.CONSTRUCTOR)hazards.add("CONSTRUCTION_LIFECYCLE_NOT_MODELED");
        if(!caller.getEnclosingElement().getEnclosingElement().getKind().equals(ElementKind.PACKAGE)
            && !caller.getEnclosingElement().getModifiers().contains(Modifier.STATIC))
            hazards.add("ENCLOSING_INSTANCE_UNKNOWN");
        if(JavaBindings.errors)hazards.add("ATTRIBUTION_ERRORS");
        final List<String> unique=new ArrayList<String>(new TreeSet<String>(hazards));
        if(!unique.isEmpty())incomplete=true;
        methods.add(obj("identity",callerId,"owner",JavaBindings.identity(caller.getEnclosingElement()),
            "binding",!JavaBindings.errors && JavaBindings.valid(caller.asType(),0)?"VERIFIED":"UNRESOLVED",
            "declaration",JavaBindings.evidence(path),"bodyAvailable",m.getBody()!=null,
            "bodyShape",unique.isEmpty()?"STRAIGHT_LINE_CANDIDATE":"INCOMPLETE",
            "hazards",unique,"transaction",transaction((ExecutableElement)caller),
            "level",level,"traversal","NOT_ASSERTED"));
        if(m.getBody()==null)return;
        new JavaBindings.Bounded() {
            void invocation() {
                TreePath site=getCurrentPath();Element element=JavaBindings.trees.getElement(site);
                String dependency=element==null?null:JavaBindings.identity(element.getEnclosingElement());
                if(!JavaBindings.selected.contains(dependency))dependency=null;
                boolean valid=!JavaBindings.errors && JavaBindings.evidence(site)!=null && element instanceof ExecutableElement
                    && JavaBindings.valid(element.asType(),0)
                    && JavaBindings.valid(JavaBindings.trees.getTypeMirror(site),0);
                // Root selection is exactly the existing seven dependency sites.
                // In callees record every call, but expand only the selected members.
                if(root) {
                    Map<String,Object> ev=JavaBindings.evidence(site);boolean selected=false;
                    for(Object r:JavaBindings.relations) {
                        Map<?,?> relation=(Map<?,?>)r;
                        if("EXECUTION_DEPENDENCY".equals(relation.get("relation")) && Objects.equals(ev,relation.get("site"))) {
                            selected=true;dependency=(String)relation.get("dependency");
                        }
                    }
                    if(!selected)return;
                }
                ExecutableElement e=element instanceof ExecutableElement?(ExecutableElement)element:null;
                TreePath target=e==null?null:JavaBindings.trees.getPath(e);
                boolean body=target!=null && target.getLeaf() instanceof MethodTree
                    && ((MethodTree)target.getLeaf()).getBody()!=null && JavaBindings.evidence(target)!=null;
                String targetId=valid?JavaBindings.identity(e):null;
                String dispatch=e==null?"UNKNOWN":dispatch(e);
                boolean fixed=valid && exact(e);
                String reason=!valid?"BINDING_UNRESOLVED":!body?"BODY_UNAVAILABLE":!fixed?"VIRTUAL_TARGET_UNKNOWN":"DECLARATION_AND_BODY_RECOVERED";
                Tree leaf=site.getLeaf();int arity=leaf instanceof NewClassTree?((NewClassTree)leaf).getArguments().size():((MethodInvocationTree)leaf).getArguments().size();
                List<String> limits=new ArrayList<String>();
                if(JavaBindings.evidence(site)==null)limits.add("GENERATED_OR_IMPLICIT_CALL");
                if(!valid)limits.add("BINDING_UNRESOLVED");
                if(!body)limits.add("BODY_UNAVAILABLE");
                if(!fixed)limits.add("RUNTIME_DISPATCH_UNKNOWN");
                if(arity!=0)limits.add("ARGUMENT_EXECUTION_NOT_MODELED");
                if(leaf instanceof NewClassTree)limits.add("CONSTRUCTION_LIFECYCLE_NOT_MODELED");
                if(!unique.isEmpty())limits.add("CALLER_BODY_INCOMPLETE");
                if(valid)limits.addAll(initialization(e.getEnclosingElement()));
                if(valid && body && (root || admitted(e)) && !seen.contains(targetId)) {
                    if(seen.size()>=32 || level>=16)limits.add("EXECUTION_BUDGET");
                    else {seen.add(targetId);pending.put(targetId,target);}
                } else if(valid && body && !root && !admitted(e))limits.add("OUTSIDE_SELECTED_CLOSURE");
                // This is a recovery witness, never permission to execute the site.
                incomplete=true;
                sites.add(obj("caller",callerId,"target",targetId,
                    "owner",valid?JavaBindings.identity(e.getEnclosingElement()):null,
                    "dependency",dependency,
                    "site",JavaBindings.evidence(site),"declaration",target==null?null:JavaBindings.evidence(target),
                    "binding",valid?"VERIFIED":"UNRESOLVED","dispatch",dispatch,
                    "dispatchCertainty",fixed?"DECLARATION_EXACT":"UNKNOWN",
                    "runtimeReceiver","UNKNOWN","bodyAvailable",body,"reason",reason,
                    "arity",arity,"level",level,"position","SOURCE_SITE_ONLY",
                    "limits",new ArrayList<String>(new TreeSet<String>(limits)),"traversal","NOT_ASSERTED"));
            }
            @Override public Void visitMethodInvocation(MethodInvocationTree t,Void p){invocation();return super.visitMethodInvocation(t,p);}
            @Override public Void visitNewClass(NewClassTree t,Void p){invocation();return super.visitNewClass(t,p);}
            @Override public Void visitClass(ClassTree t,Void p){incomplete=true;return null;}
            @Override public Void visitLambdaExpression(LambdaExpressionTree t,Void p){incomplete=true;return null;}
        }.scan(new TreePath(path,m.getBody()),null);
    }
    static Map<String,Object> collect(TreePath entry) {
        seen.add(JavaBindings.identity(JavaBindings.trees.getElement(entry)));
        scan(entry,true,0);
        int level=1;
        while(!pending.isEmpty()) {
            List<TreePath> batch=new ArrayList<TreePath>(pending.values());pending.clear();
            for(TreePath path:batch)scan(path,false,level);
            level++;
        }
        // A previously encountered declaration is sharing, not necessarily a cycle.
        // Mark only edges whose target can reach their caller in this bounded graph.
        Map<String,Set<String>> graph=new HashMap<String,Set<String>>();
        for(Object site:sites) {
            Map<?,?> s=(Map<?,?>)site;
            if(s.get("target")!=null)graph.computeIfAbsent((String)s.get("caller"),k->new HashSet<String>()).add((String)s.get("target"));
        }
        for(Object site:sites) {
            @SuppressWarnings("unchecked") Map<String,Object> s=(Map<String,Object>)site;
            Set<String> visited=new HashSet<String>(),queued=new HashSet<String>();List<String> queue=new ArrayList<String>();
            if(s.get("target")!=null){queue.add((String)s.get("target"));queued.add((String)s.get("target"));}
            for(int i=0;i<queue.size();i++) {
                String current=queue.get(i);if(!visited.add(current))continue;
                if(current.equals(s.get("caller"))) {
                    @SuppressWarnings("unchecked") List<String> limits=(List<String>)s.get("limits");
                    limits.add("CYCLIC_EXECUTION_DEPENDENCY");Collections.sort(limits);break;
                }
                for(String next:graph.getOrDefault(current,Collections.<String>emptySet()))if(queued.add(next))queue.add(next);
            }
        }
        return obj("status",incomplete?"INCOMPLETE":"COMPLETE","reason","RECOVERY_ONLY_NO_T01_EXECUTION_PROJECTION",
            "methods",methods,"sites",sites,"closureBound",32,"depthBound",16,
            "transactionTraversal","NOT_ASSERTED");
    }
}
