package fixture;
public class Good {
    interface Relevant { int value(); }
    static class Base { public int inherited() { return 1; } }
    static final class Result extends Base implements Relevant {
        Result next; // cyclic type reference, never recursively expanded
        Result() {}
        public int value() { return 1; }
    }
    static class Failure extends RuntimeException {
        Failure(String message) { super(message); }
    }
    class Inner { Inner() {} }
    static class Irrelevant { void unused() { unused(); } }
    static Result produce() { return new Result(); }
    static Result produce(String ignored) { return new Result(); }
    public void run() {
        Result r = produce();
        r.value();
        r.inherited();
        if (r.value() == 0) throw new Failure("HYBRID_SECRET_ARGUMENT");
    }
    public void six(String a, String b, String c, String d, String e, String f) {
        Result r = produce(a);
    }
    public void inner() { Inner x = new Inner(); }
    public void cycle() { cycle(); Result r = produce(); }
    public void zero() {}
}
