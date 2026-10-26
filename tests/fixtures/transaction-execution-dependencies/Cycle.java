package fixture;
public class Cycle {
    static class Nested {
        static void first() { second(); }
        static void second() { first(); }
    }
    public void run() { Nested.first(); Nested.first(); }
}
