package fixture;
public class Unique {
    static class Nested {
        static void work(String value) {}
        static void work(Integer value) {}
    }
    public void run() { Nested.work("EXEC_SECRET_LITERAL"); }
}
