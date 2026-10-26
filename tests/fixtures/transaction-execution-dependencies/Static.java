package fixture;
public class Static {
    static class Nested { static void work() {} }
    public void run() { Nested.work(); }
}
