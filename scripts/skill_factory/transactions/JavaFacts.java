import java.io.*;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;
import javax.tools.*;
import com.sun.source.tree.*;
import com.sun.source.util.*;

/** Parse only: never analyze, generate, load target classes or run processors. */
public final class JavaFacts {
    static Trees trees;
    static CompilationUnitTree unit;
    static Map<String,String> imports;
    static Set<String> typeParameters = new HashSet<String>();
    static Set<String> declaredTypes = new HashSet<String>();
    static String packageName;
    static List<Object> classes = new ArrayList<Object>();
    static Object jsonValue(Object value) { return value; }
    static Map<String,Object> obj(Object... args) {
        Map<String,Object> m = new LinkedHashMap<String,Object>();
        for (int i=0;i<args.length;i+=2) m.put((String)args[i],args[i+1]);
        return m;
    }
    static String qualify(String name) {
        if (typeParameters.contains(name)) return "UNKNOWN_TYPE_PARAMETER:"+name;
        if (imports.containsKey(name)) return imports.get(name);
        int dot=name.indexOf('.');
        if (dot>0 && imports.containsKey(name.substring(0,dot)))
            return imports.get(name.substring(0,dot))+name.substring(dot);
        return name;
    }
    // Declaration identity only; no attribution, class loading or argument binding.
    static String parameterType(Tree type, Set<String> variables) {
        if (type instanceof AnnotatedTypeTree)
            return parameterType(((AnnotatedTypeTree)type).getUnderlyingType(),variables);
        if (type instanceof ArrayTypeTree) {
            String element=parameterType(((ArrayTypeTree)type).getType(),variables);
            return element==null?null:element+"[]";
        }
        if (type instanceof ParameterizedTypeTree) {
            ParameterizedTypeTree generic=(ParameterizedTypeTree)type;
            String base=parameterType(generic.getType(),variables);
            if (base==null) return null;
            List<String> args=new ArrayList<String>();
            for (Tree argument:generic.getTypeArguments()) {
                String name=parameterType(argument,variables);
                if (name==null) return null;
                args.add(name);
            }
            return base+"<"+String.join(",",args)+">";
        }
        if (type instanceof PrimitiveTypeTree) return type.toString();
        if (type instanceof IdentifierTree) {
            String name=((IdentifierTree)type).getName().toString();
            if (variables.contains(name)) return null;
            if (imports.containsKey(name)) return imports.get(name);
            if (declaredTypes.contains(packageName+name)) return packageName+name;
            Set<String> candidates=new HashSet<String>();
            if (Arrays.asList("String","Object","Boolean","Byte","Short","Integer","Long",
                    "Float","Double","Character","Number","Exception","RuntimeException").contains(name))
                candidates.add("java.lang."+name);
            for (ImportTree im:unit.getImports()) {
                if (im.isStatic()) return null;
                String imported=im.getQualifiedIdentifier().toString();
                if (!imported.endsWith(".*")) continue;
                String prefix=imported.substring(0,imported.length()-1);
                if (declaredTypes.contains(prefix+name)) candidates.add(prefix+name);
                if (prefix.equals("java.util.")) {
                    if (Arrays.asList("List","Map","Set","Collection","Optional","UUID").contains(name))
                        candidates.add(prefix+name);
                } else if (!declaredTypes.stream().anyMatch(t -> t.substring(0,t.lastIndexOf('.')+1).equals(prefix))) {
                    return null; // unobserved wildcard namespace, never guess
                }
            }
            return candidates.size()==1?candidates.iterator().next():null;
        }
        if (type instanceof MemberSelectTree) {
            String name=type.toString();
            String first=name.substring(0,name.indexOf('.'));
            if (variables.contains(first)) return null;
            if (imports.containsKey(first)) return qualify(name);
            // Fully qualified package spelling; nested types without a binding stay unsupported.
            return Character.isLowerCase(first.charAt(0))?name:null;
        }
        return null; // wildcard/type variables and other forms need a wider resolver
    }
    static String typeSyntax(Tree type) {
        if (type instanceof AnnotatedTypeTree) return typeSyntax(((AnnotatedTypeTree)type).getUnderlyingType());
        if (type instanceof IdentifierTree || type instanceof PrimitiveTypeTree) return type.toString();
        if (type instanceof MemberSelectTree)
            return typeSyntax(((MemberSelectTree)type).getExpression())+"."+((MemberSelectTree)type).getIdentifier();
        if (type instanceof ArrayTypeTree) return typeSyntax(((ArrayTypeTree)type).getType())+"[]";
        if (type instanceof ParameterizedTypeTree) {
            ParameterizedTypeTree generic=(ParameterizedTypeTree)type;
            List<String> args=new ArrayList<String>();
            for (Tree argument:generic.getTypeArguments()) args.add(typeSyntax(argument));
            return typeSyntax(generic.getType())+"<"+String.join(",",args)+">";
        }
        return "UNKNOWN_TYPE_SYNTAX";
    }
    static Map<String,Object> position(Tree tree) {
        long start=trees.getSourcePositions().getStartPosition(unit,tree);
        long end=trees.getSourcePositions().getEndPosition(unit,tree);
        return obj("file",Paths.get(unit.getSourceFile().toUri()).getFileName().toString(),
            "start",start,"end",end,"line",start<0?0:unit.getLineMap().getLineNumber(start));
    }
    static List<Object> annotations(ModifiersTree modifiers) {
        List<Object> result=new ArrayList<Object>();
        for (AnnotationTree ann:modifiers.getAnnotations()) {
            Map<String,Object> args=new LinkedHashMap<String,Object>();
            for (ExpressionTree argument:ann.getArguments()) {
                String key="value"; ExpressionTree expr=argument;
                if (argument instanceof AssignmentTree) {
                    key=((AssignmentTree)argument).getVariable().toString();
                    expr=((AssignmentTree)argument).getExpression();
                }
                Object literal=expr instanceof LiteralTree?((LiteralTree)expr).getValue():null;
                args.put(key,obj("kind",expr.getKind().toString(),"literal",literal,
                    "text",qualify(expr.toString())));
            }
            result.add(obj("type",qualify(ann.getAnnotationType().toString()),"args",args,"evidence",position(ann)));
        }
        return result;
    }
    static List<String> flags(ModifiersTree modifiers) {
        List<String> f=new ArrayList<String>();
        for (javax.lang.model.element.Modifier m:modifiers.getFlags()) f.add(m.toString());
        return f;
    }
    static void parseClass(ClassTree cls, String pkg) {
        List<Object> fields=new ArrayList<Object>(), methods=new ArrayList<Object>();
        final List<String> dispatchHazards=new ArrayList<String>();
        typeParameters=new HashSet<String>();
        for (TypeParameterTree parameter:cls.getTypeParameters())
            typeParameters.add(parameter.getName().toString());
        if (!typeParameters.isEmpty()) dispatchHazards.add("UNRESOLVED_TYPE_PARAMETERS");
        if (unit.getImports().stream().anyMatch(im -> im.isStatic()))
            dispatchHazards.add("UNRESOLVED_STATIC_IMPORT");
        Set<String> importedNames=new HashSet<String>();
        for (ImportTree im:unit.getImports()) {
            String name=im.getQualifiedIdentifier().toString();
            if (!name.endsWith(".*") && !importedNames.add(name.substring(name.lastIndexOf('.')+1)))
                dispatchHazards.add("AMBIGUOUS_IMPORT");
        }
        // Do not resolve nested/local/anonymous types. Record their omission even
        // in field initializers and method bodies, where parseClass never visits.
        new TreeScanner<Void,Void>() {
            @Override public Void visitClass(ClassTree nested,Void unused) {
                if (nested!=cls) {
                    if (dispatchHazards.isEmpty()) dispatchHazards.add("UNEXTRACTED_APPLICATION_TYPE");
                    return null;
                }
                return super.visitClass(nested,unused);
            }
        }.scan(cls,null);
        List<String> parents=new ArrayList<String>();
        if (cls.getExtendsClause()!=null) parents.add(qualify(cls.getExtendsClause().toString()));
        for (Tree p:cls.getImplementsClause()) parents.add(qualify(p.toString()));
        for (Tree member:cls.getMembers()) {
            if (member instanceof VariableTree) {
                VariableTree f=(VariableTree)member;
                NewClassTree allocation=f.getInitializer() instanceof NewClassTree?(NewClassTree)f.getInitializer():null;
                String spelling=f.getType().toString();
                // Only a single-type import has priority independent of unobserved
                // same-package classpath types. Qualified package/type prefixes
                // require attribution; do not guess their namespace here.
                boolean explicit=spelling.equals("JdbcTemplate") &&
                    "org.springframework.jdbc.core.JdbcTemplate".equals(imports.get(spelling));
                fields.add(obj("name",f.getName().toString(),"type",qualify(spelling),
                    "flags",flags(f.getModifiers()),
                    "allocation",allocation==null?null:obj("type",qualify(allocation.getIdentifier().toString()),
                        "explicitType",explicit && allocation.getIdentifier().toString().equals(spelling),
                        "arity",allocation.getArguments().size(),"anonymous",allocation.getClassBody()!=null,
                        "evidence",position(allocation)),
                    "annotations",annotations(f.getModifiers()),"initialized",f.getInitializer()!=null,
                    "evidence",position(f)));
            } else if (member instanceof MethodTree) {
                MethodTree m=(MethodTree)member;
                List<Object> parameters=new ArrayList<Object>();
                Set<String> variables=new HashSet<String>(typeParameters);
                for (TypeParameterTree parameter:m.getTypeParameters()) variables.add(parameter.getName().toString());
                for (VariableTree parameter:m.getParameters()) {
                    String resolved=parameterType(parameter.getType(),variables);
                    String syntax=typeSyntax(parameter.getType());
                    boolean declarationOnly=resolved==null && parameter.getType() instanceof IdentifierTree &&
                        !variables.contains(syntax) && unit.getImports().stream().anyMatch(im ->
                            !im.isStatic() && im.getQualifiedIdentifier().toString().endsWith(".*"));
                    parameters.add(obj("name",parameter.getName().toString(),
                        "type",resolved,"declaredType",syntax,
                        "typeResolution",resolved!=null?"SOURCE_NAMESPACE":declarationOnly?"DECLARED_ONLY":"UNSUPPORTED",
                        "runtimeValue","UNKNOWN",
                        "evidence",position(parameter)));
                }
                if (!m.getTypeParameters().isEmpty()) dispatchHazards.add("UNRESOLVED_TYPE_PARAMETERS");
                final List<Object> calls=new ArrayList<Object>();
                final Set<MethodInvocationTree> statementCalls=Collections.newSetFromMap(new IdentityHashMap<MethodInvocationTree,Boolean>());
                List<String> hazards=new ArrayList<String>();
                if (m.getBody()==null) hazards.add("missing-body");
                else {
                    List<? extends StatementTree> statements=m.getBody().getStatements();
                    for (int i=0;i<statements.size();i++) {
                        StatementTree statement=statements.get(i);
                        if (statement instanceof ExpressionStatementTree &&
                            ((ExpressionStatementTree)statement).getExpression() instanceof MethodInvocationTree)
                            statementCalls.add((MethodInvocationTree)((ExpressionStatementTree)statement).getExpression());
                        if (statement instanceof ReturnTree && ((ReturnTree)statement).getExpression()==null && i==statements.size()-1) continue;
                        if (!(statement instanceof ExpressionStatementTree) ||
                            !(((ExpressionStatementTree)statement).getExpression() instanceof MethodInvocationTree))
                            hazards.add("unsupported-control-or-expression");
                    }
                    new TreeScanner<Void,Void>() {
                        @Override public Void visitLambdaExpression(LambdaExpressionTree lambda,Void unused) {
                            hazards.add("lambda-execution-not-established"); return null;
                        }
                        @Override public Void visitMemberReference(MemberReferenceTree reference,Void unused) {
                            hazards.add("method-reference-execution-not-established"); return null;
                        }
                        @Override public Void visitMethodInvocation(MethodInvocationTree call,Void unused) {
                            // Source-order sequence is claimed only for the restricted zero-argument body shape.
                            super.visitMethodInvocation(call,unused);
                            String receiver="", name=call.getMethodSelect().toString();
                            if (call.getMethodSelect() instanceof MemberSelectTree) {
                                MemberSelectTree select=(MemberSelectTree)call.getMethodSelect();
                                receiver=select.getExpression().toString();name=select.getIdentifier().toString();
                            }
                            List<Object> arguments=new ArrayList<Object>();
                            for (ExpressionTree argument:call.getArguments()) {
                                arguments.add(obj("kind",argument.getKind().toString(),
                                    "literal",argument instanceof LiteralTree?((LiteralTree)argument).getValue():null,
                                    "evidence",position(argument)));
                            }
                            calls.add(obj("receiver",receiver,"name",name,"arity",call.getArguments().size(),
                                "arguments",arguments,"statementCall",statementCalls.contains(call),"evidence",position(call)));
                            return null;
                        }
                        @Override public Void visitClass(ClassTree nested,Void unused) { return null; }
                    }.scan(m.getBody(),null);
                }
                methods.add(obj("name",m.getName().toString(),"arity",m.getParameters().size(),
                    "parameters",parameters,
                    "returnType",m.getReturnType()==null?"":qualify(m.getReturnType().toString()),
                    "annotations",annotations(m.getModifiers()),"flags",flags(m.getModifiers()),
                    "hazards",hazards,"calls",calls,"evidence",position(m)));
            } else if (member instanceof ClassTree || member instanceof BlockTree) {
                parents.add("UNKNOWN_NESTED_CLASS_OR_INITIALIZER");
            }
        }
        classes.add(obj("name",pkg+cls.getSimpleName(),"simpleName",cls.getSimpleName().toString(),
            "kind",cls.getKind().toString(),"flags",flags(cls.getModifiers()),"parents",parents,
            "dispatchHazards",dispatchHazards,
            "annotations",annotations(cls.getModifiers()),"fields",fields,"methods",methods,"evidence",position(cls)));
    }
    static String json(Object value) {
        if (value==null) return "null";
        if (value instanceof String) {
            StringBuilder b=new StringBuilder("\"");
            for (char c:((String)value).toCharArray()) {
                if (c=='"'||c=='\\') b.append('\\').append(c);
                else if(c<32) b.append(String.format("\\u%04x",(int)c));
                else b.append(c);
            }
            return b.append('"').toString();
        }
        if(value instanceof Map) {
            List<String> pairs=new ArrayList<String>();
            for(Object entryObject:((Map<?,?>)value).entrySet()) {
                Map.Entry<?,?> e=(Map.Entry<?,?>)entryObject;pairs.add(json(e.getKey())+":"+json(e.getValue()));
            }
            return "{"+String.join(",",pairs)+"}";
        }
        if(value instanceof Iterable) {
            List<String> items=new ArrayList<String>();for(Object item:(Iterable<?>)value)items.add(json(item));
            return "["+String.join(",",items)+"]";
        }
        return value.toString();
    }
    public static void main(String[] args) throws Exception {
        JavaCompiler compiler=ToolProvider.getSystemJavaCompiler();
        if(compiler==null)throw new IllegalStateException("JDK compiler required");
        DiagnosticCollector<JavaFileObject> diagnostics=new DiagnosticCollector<JavaFileObject>();
        StandardJavaFileManager manager=compiler.getStandardFileManager(diagnostics,null,StandardCharsets.UTF_8);
        try {
            JavacTask task=(JavacTask)compiler.getTask(null,manager,diagnostics,
                Arrays.asList("-proc:none","-encoding","UTF-8"),null,manager.getJavaFileObjects(args));
            Iterable<? extends CompilationUnitTree> units=task.parse();
            trees=Trees.instance(task);
            List<CompilationUnitTree> parsedUnits=new ArrayList<CompilationUnitTree>();
            for(CompilationUnitTree parsed:units) {
                parsedUnits.add(parsed);
                String pkg=parsed.getPackageName()==null?"":parsed.getPackageName().toString()+".";
                for(Tree type:parsed.getTypeDecls()) if(type instanceof ClassTree)
                    declaredTypes.add(pkg+((ClassTree)type).getSimpleName());
            }
            for(CompilationUnitTree parsed:parsedUnits) {
                unit=parsed;imports=new HashMap<String,String>();
                for(ImportTree im:unit.getImports()) {
                    String type=im.getQualifiedIdentifier().toString();
                    if(!type.endsWith(".*"))imports.put(type.substring(type.lastIndexOf('.')+1),type);
                }
                String pkg=unit.getPackageName()==null?"":unit.getPackageName().toString()+".";
                packageName=pkg;
                for(Tree type:unit.getTypeDecls()) if(type instanceof ClassTree)parseClass((ClassTree)type,pkg);
            }
            List<String> errors=new ArrayList<String>();
            for(Diagnostic<?> diagnostic:diagnostics.getDiagnostics())
                if(diagnostic.getKind()==Diagnostic.Kind.ERROR)
                    errors.add(diagnostic.getCode()+" at line "+diagnostic.getLineNumber());
            System.out.println(json(obj("classes",classes,"errors",errors)));
        } finally {manager.close();}
    }
}
