package fixture;
public class Ambiguous {
    static class Nested {
        static void work(String value) {}
        static void work(Integer value) {}
    }
    public void run() { Nested.work(null); }
}
