// Independent javac/javap oracle: compile synthetic fixtures only, never execute.
class OracleTypes {
    static class StaticMember { static void work() {} }
    class InnerMember { void work() {} }
    static class Derived extends Base implements Contract {}
    void local() { class Local {} }
    void anonymous() { new Runnable() { public void run() {} }; }
}
class Base {}
interface Contract {}
