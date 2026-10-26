import java.util.*;
import javax.lang.model.element.*;
import com.sun.source.tree.*;
import com.sun.source.util.*;

/** Closed source rule: harmless int literals, then one private self entry.
 * Runs within HYBRID's attributed task. Does not visit the callee or resume.
 */
final class JavaLocalEntry {
    static Map<String,Object> obj(Object... a) { return JavaBindings.obj(a); }
    static Map<String,Object> blocked(String reason) { return obj("rule","PRIVATE_SELF_PREFIX_V1","status","BLOCKED","reason",reason); }
    static Map<String,Object> collect(TreePath entry) {
        if(JavaBindings.errors)return blocked("ATTRIBUTION_ERRORS");
        MethodTree method=(MethodTree)entry.getLeaf();
        ExecutableElement caller=(ExecutableElement)JavaBindings.trees.getElement(entry);
        if(caller.getModifiers().contains(Modifier.STATIC) || method.getBody()==null)
            return blocked("INSTANCE_BODY_ENTRY_REQUIRED");
        List<Object> prefix=new ArrayList<Object>();
        TreePath body=new TreePath(entry,method.getBody());
        for(StatementTree statement:method.getBody().getStatements()) {
            if(prefix.size()>=32)return blocked("PREFIX_BUDGET");
            TreePath sp=new TreePath(body,statement);
            ExpressionTree expression=null;
            if(statement instanceof VariableTree) {
                VariableTree v=(VariableTree)statement;
                expression=v.getInitializer();
                if(expression!=null && expression.getKind()==Tree.Kind.INT_LITERAL && v.getType().getKind()==Tree.Kind.PRIMITIVE_TYPE
                    && v.getType().toString().equals("int")) {
                    prefix.add(obj("kind","INT_LITERAL_LOCAL","evidence",JavaBindings.evidence(sp)));continue;
                }
            } else if(statement instanceof ExpressionStatementTree)
                expression=((ExpressionStatementTree)statement).getExpression();
            if(!(expression instanceof MethodInvocationTree))return blocked("PREFIX_EVALUATION_NOT_CLOSED");
            TreePath callPath=new TreePath(sp,expression);
            Element element=JavaBindings.trees.getElement(callPath);
            if(!(element instanceof ExecutableElement) || !JavaBindings.valid(element.asType(),0))return blocked("BINDING_UNRESOLVED");
            ExecutableElement target=(ExecutableElement)element;
            MethodInvocationTree call=(MethodInvocationTree)expression;
            ExpressionTree receiver=call.getMethodSelect();
            if(receiver instanceof MemberSelectTree) {
                ExpressionTree selected=((MemberSelectTree)receiver).getExpression();
                if(!(selected instanceof IdentifierTree) || !((IdentifierTree)selected).getName().contentEquals("this"))
                    return blocked("RECEIVER_NOT_PROVEN_THIS");
            } else if(!(receiver instanceof IdentifierTree))return blocked("RECEIVER_NOT_PROVEN_THIS");
            if(!target.getModifiers().contains(Modifier.PRIVATE) || target.getModifiers().contains(Modifier.STATIC)
                || !target.getEnclosingElement().equals(caller.getEnclosingElement()))return blocked("PRIVATE_DIRECT_DISPATCH_REQUIRED");
            if(target.getModifiers().contains(Modifier.SYNCHRONIZED) || target.getModifiers().contains(Modifier.NATIVE))
                return blocked("CALLEE_ENTRY_MECHANISM_NOT_CLOSED");
            if(target.isVarArgs() || !call.getTypeArguments().isEmpty() || call.getArguments().size()!=target.getParameters().size())
                return blocked("ARGUMENT_CONVERSION_NOT_CLOSED");
            List<Object> arguments=new ArrayList<Object>();
            for(int i=0;i<call.getArguments().size();i++) {
                ExpressionTree arg=call.getArguments().get(i);TreePath ap=new TreePath(callPath,arg);
                String type=JavaBindings.trees.getTypeMirror(ap).toString();
                if(!type.equals(target.getParameters().get(i).asType().toString()))return blocked("ARGUMENT_CONVERSION_NOT_CLOSED");
                Element source=JavaBindings.trees.getElement(ap);
                int parameter=caller.getParameters().indexOf(source);
                if(arg instanceof IdentifierTree && parameter>=0)
                    arguments.add(obj("kind","FORMAL_PARAMETER_READ","parameter",parameter,"type",type,"evidence",JavaBindings.evidence(ap)));
                else if(arg.getKind()==Tree.Kind.BOOLEAN_LITERAL)
                    arguments.add(obj("kind","BOOLEAN_LITERAL","value",((LiteralTree)arg).getValue(),"type",type,"evidence",JavaBindings.evidence(ap)));
                else return blocked("ARGUMENT_EVALUATION_NOT_CLOSED");
            }
            TreePath declaration=JavaBindings.trees.getPath(target);
            if(declaration==null || JavaBindings.evidence(callPath)==null || JavaBindings.evidence(declaration)==null)
                return blocked("SOURCE_PROVENANCE_REQUIRED");
            return obj("rule","PRIVATE_SELF_PREFIX_V1","status","QUALIFIED",
                "caller",JavaBindings.identity(caller),"callerDeclaration",JavaBindings.evidence(entry),
                "target",JavaBindings.identity(target),"targetDeclaration",JavaBindings.evidence(declaration),
                "callSite",JavaBindings.evidence(callPath),"statement",JavaBindings.evidence(sp),
                "prefix",prefix,"receiver","THIS","dispatch","DIRECT","dispatchCertainty","DECLARATION_EXACT",
                "arguments",arguments,"evaluationOrder","PREFIX_RECEIVER_ARGUMENTS_LEFT_TO_RIGHT_ENTRY",
                "lifecycle","NO_NEW_ACTIVE_USE_BEFORE_PRIVATE_INSTANCE_ENTRY");
        }
        return blocked("NO_QUALIFIABLE_ENTRY");
    }
}
