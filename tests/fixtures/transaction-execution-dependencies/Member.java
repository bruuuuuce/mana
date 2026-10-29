package fixture;
public class Member {
    class Nested { void work() {} }
    public void run() { new Nested().work(); }
}
